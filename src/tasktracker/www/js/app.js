/* TaskTracker - Vue 2 entry point.

   - Hash-mode router over three screens: the projects table, one project's
     board, and settings.
   - Minimal Vuex: the settings the server owns, the counts the bar reports,
     the toasts, and the theme.
   - Shared formatters, so every screen renders a timestamp the same way.
   - Shared error unwrapping, so no screen shows the operator raw JSON.
*/

Vue.use(httpVueLoader);
Vue.use(Vuex);

/* The API reports every timestamp as a unix epoch float. One representation on
   the wire, formatted here, so no two screens can disagree about what a date
   means. */
Vue.filter('datetime', function (value) {
  if (value === null || value === undefined || value === '') return '-';
  var when = new Date(Number(value) * 1000);
  if (isNaN(when.getTime())) return '-';
  var pad = function (n) { return (n < 10 ? '0' : '') + n; };
  return when.getFullYear() + '-' + pad(when.getMonth() + 1) + '-' + pad(when.getDate()) +
         ' ' + pad(when.getHours()) + ':' + pad(when.getMinutes());
});

/* How long ago, in the largest unit that still says something.

   The projects table is read to answer "what was I working on", and a column of
   absolute stamps makes that a subtraction the operator does by eye for every
   row. The exact stamp is still there, in the row's title attribute, for the
   times the answer is "which of these two was later". */
Vue.filter('ago', function (value) {
  if (value === null || value === undefined || value === '') return '-';
  var seconds = Math.floor(Date.now() / 1000 - Number(value));
  if (!isFinite(seconds)) return '-';
  // A clock that has drifted, or a row written a moment ago by another process.
  // "in 3 seconds" is a worse answer than "just now".
  if (seconds < 60) return 'just now';
  var steps = [
    [60, 'minute'], [24, 'hour'], [7, 'day'], [4.348, 'week'], [12, 'month'],
  ];
  var count = seconds;
  var unit = 'second';
  for (var i = 0; i < steps.length; i++) {
    if (count < steps[i][0]) break;
    count = count / steps[i][0];
    unit = steps[i][1];
  }
  count = Math.floor(count);
  if (unit === 'second') return 'just now';
  return count + ' ' + unit + (count === 1 ? '' : 's') + ' ago';
});

/* The one place an axios failure becomes a sentence for a bar or a toast.

   The API answers every failure as {"error": {"message": …}} - including the
   static mount's 404s and the validation failures FastAPI would otherwise send
   as a list of dictionaries. This still checks the other shapes, because a
   proxy in front of the panel answers in its own. */
const apiError = function (err) {
  var data = err && err.response && err.response.data;
  if (data && typeof data === 'object') {
    if (data.error && data.error.message) return String(data.error.message);
    if (typeof data.error === 'string' && data.error) return data.error;
    if (typeof data.detail === 'string' && data.detail) return data.detail;
  }
  if (err && err.message) return String(err.message);
  return 'the request failed';
};
Vue.prototype.$apiError = apiError;

/* Browser storage, or null where there is none.

   A browser with site data switched off throws on the property itself rather
   than answering undefined. Either way the panel has to start: the preference
   becomes the default, not a ReferenceError thrown before the router exists. */
const box = function () {
  try {
    return typeof localStorage === 'undefined' ? null : localStorage;
  } catch (err) {
    return null;
  }
};

const readStored = function (key) {
  var store = box();
  if (!store) return null;
  try {
    return store.getItem(key);
  } catch (err) {
    return null;
  }
};

const writeStored = function (key, value) {
  var store = box();
  if (!store) return false;
  try {
    store.setItem(key, value);
    return true;
  } catch (err) {
    // A full quota, or storage in read-only mode. Reported rather than
    // swallowed: the alternative is a control that silently forgets itself.
    return false;
  }
};

/* Light or dark.

   A view preference belonging to this browser rather than to the board, so it
   is stored here and not in the settings table - a colleague opening the same
   panel gets their own room's answer. Only the two spellings are accepted on
   the way in as well as on the way out: the stored text is hand-editable, and
   `data-theme="sepia"` is a document that matches neither half of the palette
   and renders with no theme at all. */
const THEME_KEY = 'tt.theme';
const THEMES = ['light', 'dark'];

const systemTheme = function () {
  try {
    if (typeof window === 'undefined' || !window.matchMedia) return 'light';
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  } catch (err) {
    return 'light';
  }
};

const readTheme = function () {
  var stored = readStored(THEME_KEY);
  return THEMES.indexOf(stored) === -1 ? systemTheme() : stored;
};

/* Both attributes, on the document element. `data-theme` is what css/main.css
   keys its dark palette on; `data-bs-theme` is what Bootstrap 5.3 keys its own
   on, and every dialog and input on these screens is Bootstrap's - setting only
   ours would give a dark page full of white modals. */
const applyTheme = function (theme) {
  var root = (typeof document === 'undefined' || !document) ? null : document.documentElement;
  if (!root || !root.setAttribute) return;
  root.setAttribute('data-theme', theme);
  root.setAttribute('data-bs-theme', theme);
};

/* Applied here, as the file loads, and not from a mounted hook. Set later,
   every load would paint the light palette, hold it for a round trip, and flip
   - and that flash is on every page the operator opens all day. */
const startingTheme = readTheme();
applyTheme(startingTheme);

/* Board or table, per project.

   Per project rather than one setting for the whole panel: a repository with
   four cards is read as a board and one with sixty is read as a list, and an
   operator who switched once should not have to switch back every time they
   move between the two. */
const VIEW_KEY = 'tt.view';
const VIEWS = ['board', 'table'];

const readView = function (projectId) {
  var stored = readStored(VIEW_KEY + '.' + projectId);
  return VIEWS.indexOf(stored) === -1 ? 'board' : stored;
};
Vue.prototype.$readView = readView;
Vue.prototype.$saveView = function (projectId, view) {
  var wanted = VIEWS.indexOf(view) === -1 ? 'board' : view;
  return writeStored(VIEW_KEY + '.' + projectId, wanted);
};

/* How often the screens re-read the board.

   The panel is the second window onto a board Claude writes to while it works,
   so a screen that only refreshed on navigation would be wrong for as long as
   it was open - which is the whole time. Three seconds against a loopback bind
   is one small query; anything faster would be polling for its own sake. */
const POLL_MS = 3000;
Vue.prototype.$pollMs = POLL_MS;

const store = new Vuex.Store({
  state: {
    theme: startingTheme,
    // What the server owns. Held here rather than fetched per screen so the
    // board and the settings screen cannot disagree about how long a finished
    // card is drawn for.
    settings: { done_hide_days: null },
    /* Every project with its four counts, and the queued total the bar
       reports.

       Held in the store and polled by the header rather than by the projects
       screen, because the bar carries the total on every screen - including the
       board, which knows about one project. One poll feeds both, and the number
       in the bar cannot disagree with the table under it. */
    projects: [],
    queuedTotal: 0,
    /* Why the last projects poll failed, or the empty string.

       Kept in the store rather than raised by whoever polled, because the poll
       is the header's and the screen that has to report it is the projects
       table. Without this the table would keep drawing the last good answer
       while the server was down - a list that lies, which is worse than an
       empty one. */
    projectsError: '',
    toasts: [],
    nextToast: 1,
  },
  mutations: {
    settings: function (state, settings) { state.settings = settings; },
    projectsError: function (state, message) { state.projectsError = message; },
    projects: function (state, projects) {
      state.projects = projects;
      state.queuedTotal = projects.reduce(function (total, project) {
        return total + (project.queued || 0);
      }, 0);
    },
    theme: function (state, theme) { state.theme = theme; },
    toast: function (state, toast) {
      state.toasts.push({ id: state.nextToast++, kind: toast.kind, text: toast.text });
    },
    dismiss: function (state, id) {
      state.toasts = state.toasts.filter(function (toast) { return toast.id !== id; });
    },
  },
  actions: {
    /* The settings, read once and shared.

       Failing quietly on purpose: every screen dispatches this on mount, and a
       board that refused to render because the settings request lost a race
       would be a board that fails for a reason unrelated to anything on it. The
       cards are still correct - the server has already applied the setting when
       it chose which ones to send. */
    settings: function (context) {
      return axios.get('/api/settings').then(function (answer) {
        context.commit('settings', answer.data);
        return answer.data;
      }).catch(function () { return null; });
    },

    /* The projects list, for the table that shows it and the total in the bar.

       The failure is recorded on `projectsError` and re-raised, unlike the
       settings above which fail silently. The header - which only wants the
       number for the bar - catches it; the projects screen renders the
       recorded message, because a list quietly showing the last good answer
       while the server is down is a screen that lies. */
    projects: function (context) {
      return axios.get('/api/projects').then(function (answer) {
        context.commit('projects', answer.data.projects || []);
        context.commit('projectsError', '');
        return context.state.projects;
      }).catch(function (err) {
        context.commit('projectsError', apiError(err));
        return Promise.reject(err);
      });
    },
  },
});

/* One toast, from anywhere. `$toast('success', 'Saved')`. */
Vue.prototype.$toast = function (kind, text) {
  store.commit('toast', { kind: kind, text: text });
};

Vue.prototype.$saveTheme = function (next) {
  var theme = THEMES.indexOf(next) === -1 ? 'light' : next;
  var kept = writeStored(THEME_KEY, theme);
  store.commit('theme', theme);
  applyTheme(theme);
  return kept;
};

/* A screen, loaded when it is first opened.

   `MissingScreen` rather than a blank page: a .vue that failed to load leaves
   the router with nothing to render, and a panel showing an empty frame is one
   the operator reloads three times before opening the console. */
const MissingScreen = {
  template:
    '<div class="tt-page"><div class="tt-alert tt-alert-error">' +
    '<i class="fa fa-circle-exclamation"></i>' +
    '<span class="tt-alert-msg">This screen could not be loaded. ' +
    'The panel files may be out of step with the server - reload the page.</span>' +
    '</div></div>',
};

const screen = function (name) {
  var load = httpVueLoader('/views/' + name + '.vue');
  return function () {
    return { component: load(), error: MissingScreen, timeout: 20000 };
  };
};

/* The furniture every screen needs, registered once.

   `tt-alerts` is the four message bars, bound with `.sync` to strings the
   screen owns. `tt-confirm` is the only dialog allowed in front of a delete;
   `window.confirm` is what it replaces and no screen may go back to it - it
   blocks the event loop, so the poll behind it piles up. `tt-task-dialog` is
   the one editor both views of the board open. Registered here rather than in a
   `components:` block per screen, which is one more place for two copies of the
   same control to drift apart. */
Vue.component('tt-alerts', httpVueLoader('/views/Alerts.vue'));
Vue.component('tt-confirm', httpVueLoader('/views/Confirm.vue'));
Vue.component('tt-task-dialog', httpVueLoader('/views/TaskDialog.vue'));

const router = new VueRouter({
  mode: 'hash',
  routes: [
    { path: '/', redirect: '/projects' },
    { path: '/projects', component: screen('Projects') },
    { path: '/projects/:id', component: screen('Board'), props: true },
    { path: '/settings', component: screen('Settings') },
    { path: '*', redirect: '/projects' },
  ],
});

/* Every programmatic navigation goes through here. vue-router 3 rejects the
   promise it returns when a navigation is redirected, cancelled, or already
   where it was asked to go - all ordinary here, none of them worth an
   "Uncaught (in promise)" in the console. */
const goto = function (target) {
  var leaving = router.push(target);
  if (leaving && leaving.catch) leaving.catch(function () {});
};
Vue.prototype.$goto = goto;

/* What the browser tab says: one name and the screen you are on, so a window
   with four tabs open on this panel can be told apart without clicking through
   them. Set from the route rather than by each screen - a screen that forgot
   would leave the previous one's name in the tab. */
router.afterEach(function (to) {
  if (to.path === '/projects') document.title = 'TaskTracker · Projects';
  else if (to.path === '/settings') document.title = 'TaskTracker · Settings';
  else document.title = 'TaskTracker';
});

const App = {
  template:
    '<div>' +
    '<tt-header></tt-header>' +
    '<tt-toaster></tt-toaster>' +
    '<router-view :key="$route.path" />' +
    '</div>',
  components: {
    'tt-header': httpVueLoader('/views/Header.vue'),
    'tt-toaster': httpVueLoader('/views/Toaster.vue'),
  },
};

new Vue({ router: router, store: store, render: function (h) { return h(App); } }).$mount('#app');
