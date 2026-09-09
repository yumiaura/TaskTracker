<template>
  <header class="tt-header">
    <ul>
      <li class="navbar-brand">
        <router-link to="/projects">TaskTracker</router-link>
      </li>

      <li class="nav-item" :class="{ active: tabActive('/projects') }">
        <router-link to="/projects">PROJECTS</router-link>
      </li>
      <li class="nav-item" :class="{ active: tabActive('/settings') }">
        <router-link to="/settings">SETTINGS</router-link>
      </li>

      <li class="m-auto"></li>

      <!-- How much is waiting, across every project.

           The one number worth carrying on every screen: the board answers
           "what is left here", and this answers "what is left anywhere" -
           which is the question somebody opening the panel between two pieces
           of work actually has. A link rather than a label, because a count
           you cannot get to the contents of is a number you learn to ignore.

           Hidden at zero rather than shown as "0 queued". An empty queue is
           not news, and a badge that is always there is one nobody reads. -->
      <li class="nav-item nav-status" v-if="$store.state.queuedTotal > 0">
        <router-link to="/projects" class="tt-total"
                     :title="$store.state.queuedTotal + ' tasks queued across every project'">
          {{ $store.state.queuedTotal }} queued
        </router-link>
      </li>

      <!-- Light or dark. In the bar rather than on the settings screen: it is
           the one setting changed because of the room you are sitting in, and
           a setting you have to navigate away from your work to reach is one
           you change and then have to find your way back from.

           A real <button>, so it is reachable by keyboard and announced as a
           control; the glyph alone would be a decoration to a screen reader.
           `title` and `aria-label` both name the theme it switches TO - a
           control labelled with the state it is in reads, to whoever meets it
           first, as the state it will produce. -->
      <li class="nav-item nav-theme">
        <button type="button" class="tt-theme-toggle"
                @click="toggleTheme" :title="themeAction" :aria-label="themeAction">
          <i class="fa" :class="darkTheme ? 'fa-sun' : 'fa-moon'"></i>
        </button>
      </li>
    </ul>
  </header>
</template>

<script>
/* The bar, and the one poll behind it.

   The projects list is read here rather than by the projects screen, because
   the total in this bar is on every screen - the board included, which knows
   about one project. One poll feeds both, so the number in the bar cannot
   disagree with the table under it.

   The failure is swallowed here and only here. The bar wants a number; a
   momentary failure to fetch it is not worth a message across the top of a
   board that is otherwise fine, and the projects screen - which IS the list -
   dispatches the same action itself and reports what it gets.
*/
module.exports = {
  data: function () {
    return { timer: null };
  },

  computed: {
    darkTheme: function () {
      return this.$store.state.theme === 'dark';
    },
    themeAction: function () {
      return this.darkTheme ? 'Switch to the light theme' : 'Switch to the dark theme';
    },
  },

  mounted: function () {
    this.poll();
    this.timer = setInterval(this.poll, this.$pollMs);
  },

  /* Vue 2 spelling. An interval left running after the header is torn down
     keeps a request in flight against a store no longer on screen, and in a
     hot reload it is a second timer on top of the first. */
  beforeDestroy: function () {
    if (this.timer) clearInterval(this.timer);
  },

  methods: {
    poll: function () {
      this.$store.dispatch('projects').catch(function () {});
    },

    /* The tab lights for the screens it stands for as well as for its own
       path. A board is a page of PROJECTS: without this, opening one leaves
       nothing in the row lit and the panel reads as broken rather than as one
       level down. */
    tabActive: function (path) {
      return this.$route.path === path || this.$route.path.indexOf(path + '/') === 0;
    },

    toggleTheme: function () {
      var next = this.darkTheme ? 'light' : 'dark';
      if (!this.$saveTheme(next)) {
        this.$toast('warning', 'The theme is in force, but this browser would not remember it.');
      }
    },
  },
};
</script>
