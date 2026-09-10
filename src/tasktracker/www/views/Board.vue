<template>
  <div class="tt-page">
    <div class="tt-bar">
      <h1 class="tt-bar-title">
        <router-link to="/projects" title="Back to every project">
          <i class="fa fa-chevron-left" aria-hidden="true"></i>
        </router-link>
        {{ project ? project.name : '…' }}
      </h1>
      <span class="text-muted-soft" v-if="project" :title="project.path">{{ project.path }}</span>

      <span class="tt-bar-gap"></span>

      <!-- The same cards, two ways of reading them. A pair of buttons rather
           than a select: there are two of them, they are mutually exclusive,
           and which one is in force has to be visible without opening
           anything. -->
      <div class="btn-group btn-group-sm" role="group" aria-label="How to show the tasks">
        <button type="button" class="btn btn-sm"
                :class="view === 'board' ? 'btn-primary' : 'btn-outline-secondary'"
                @click="setView('board')" title="Three columns">
          <i class="fa fa-table-columns" aria-hidden="true"></i> BOARD
        </button>
        <button type="button" class="btn btn-sm"
                :class="view === 'table' ? 'btn-primary' : 'btn-outline-secondary'"
                @click="setView('table')" title="One list">
          <i class="fa fa-list" aria-hidden="true"></i> TABLE
        </button>
      </div>

      <button type="button" class="btn btn-sm btn-primary" @click="add" title="Add a task">
        <i class="fa fa-plus" aria-hidden="true"></i> NEW TASK
      </button>
    </div>

    <tt-alerts :error.sync="error"></tt-alerts>

    <!-- Board -->
    <div class="tt-board" v-if="view === 'board'">
      <div v-for="column in columns" :key="column.status" class="tt-column" :class="column.klass">
        <div class="tt-column-head">
          <span>{{ column.title }}</span>
          <span class="tt-column-count">{{ grouped[column.status].length }}</span>
        </div>

        <div class="tt-column-body"
             :class="{ 'tt-over': dropStatus === column.status }"
             :ref="'column-' + column.status"
             @dragover.prevent="over($event, column.status)"
             @dragleave="leave($event, column.status)"
             @drop.prevent="drop(column.status)">

          <div class="tt-drop-line" v-if="lineAt(column.status, 0)"></div>

          <template v-for="(task, slot) in grouped[column.status]">
            <div class="tt-task" :key="task.id"
                 :class="{ 'tt-dragging': draggingId === task.id }"
                 draggable="true"
                 @dragstart="start($event, task)"
                 @dragend="end"
                 @dblclick="edit(task)">
              <div class="tt-task-title">{{ task.title }}</div>
              <div class="tt-task-detail" v-if="expanded[task.id] && task.detail">{{ task.detail }}</div>
              <div class="tt-task-foot">
                <span class="tt-source" :class="'tt-source-' + task.source"
                      v-if="task.source !== 'manual'"
                      :title="sourceTitle(task)">{{ task.source }}</span>
                <span :title="task.updated_at | datetime">{{ task.updated_at | ago }}</span>
                <span class="tt-task-actions">
                  <i class="fa" :class="expanded[task.id] ? 'fa-chevron-up' : 'fa-align-left'"
                     v-if="task.detail" role="button" tabindex="0"
                     :title="expanded[task.id] ? 'Hide the detail' : 'Show the detail'"
                     @click.stop="toggle(task)" @keyup.enter="toggle(task)"></i>
                  <i class="fa fa-pen" role="button" tabindex="0" title="Edit"
                     @click.stop="edit(task)" @keyup.enter="edit(task)"></i>
                  <i class="fa fa-trash text-danger" role="button" tabindex="0" title="Delete"
                     @click.stop="remove(task)" @keyup.enter="remove(task)"></i>
                </span>
              </div>
            </div>
            <div class="tt-drop-line" :key="'line-' + task.id"
                 v-if="lineAt(column.status, slot + 1)"></div>
          </template>

          <div class="tt-column-empty" v-if="!grouped[column.status].length">
            {{ column.empty }}
          </div>
        </div>
      </div>
    </div>

    <!-- Table -->
    <div class="tt-card p-0" v-else>
      <table class="table table-striped table-hover table-fixed mb-0">
        <thead>
          <tr>
            <th>TASK</th>
            <th style="width:130px">STATUS</th>
            <th style="width:90px">SOURCE</th>
            <th style="width:150px">UPDATED</th>
            <th style="width:70px"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="task in tasks" :key="task.id">
            <td class="td-ellipsis" :title="task.detail || task.title">{{ task.title }}</td>
            <!-- A select rather than a pill in this view: the table is the way
                 to work through a long list, and dragging is what the board is
                 for. The word is still the word the pill would have shown. -->
            <td>
              <select class="form-select form-select-sm"
                      :value="task.status" @change="pick(task, $event.target.value)">
                <option value="todo">TODO</option>
                <option value="queued">QUEUE</option>
                <option value="in_progress">IN PROGRESS</option>
                <option value="done">DONE</option>
              </select>
            </td>
            <td class="text-muted-soft" :title="sourceTitle(task)">{{ task.source }}</td>
            <td :title="task.updated_at | datetime">{{ task.updated_at | ago }}</td>
            <td class="td-actions">
              <i class="fa fa-pen" role="button" tabindex="0" title="Edit"
                 @click="edit(task)" @keyup.enter="edit(task)"></i>
              <i class="fa fa-trash text-danger" role="button" tabindex="0" title="Delete"
                 @click="remove(task)" @keyup.enter="remove(task)"></i>
            </td>
          </tr>
          <tr v-if="!tasks.length">
            <td colspan="5" class="text-center text-muted-soft py-3">
              Nothing on this board yet.
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <tt-task-dialog ref="editor" @saved="reload"></tt-task-dialog>
    <tt-confirm ref="confirm"></tt-confirm>
  </div>
</template>

<script>
/* One project: three columns, or the same cards as a list.

   The board is a second window onto a table Claude writes to while it works, so
   it polls. Everything else here follows from that: a poll must not move a card
   out from under a drag, and it must not renumber a column while the operator
   is reading it.
*/

/* The four columns, left to right, with what an empty one says.

   TODO is the backlog, where everything new lands; QUEUE is what was picked to
   be done next, and a card only gets there by being moved.

   The empty sentences are not "No tasks". Each column is empty for a different
   reason and only one of them is worth acting on, so each says its own thing -
   an empty queue is the good outcome, an empty done column on a busy board is
   just early in the week. */
var COLUMNS = [
  { status: 'todo', title: 'TODO', klass: 'tt-column-todo', empty: 'The backlog is empty.' },
  { status: 'queued', title: 'QUEUE', klass: 'tt-column-queued', empty: 'Nothing picked for next.' },
  {
    status: 'in_progress',
    title: 'IN PROGRESS',
    klass: 'tt-column-progress',
    empty: 'Nothing in flight.',
  },
  { status: 'done', title: 'DONE', klass: 'tt-column-done', empty: 'Nothing finished yet.' },
];

/* What each source means, said in words on hover. The badge is one lowercase
   token because the card is one line tall; the sentence is where it says what
   the token stands for, so nobody has to learn the vocabulary from the README. */
var SOURCE_TITLES = {
  todo: 'Mirrored from Claude’s own todo list while it worked.',
  mcp: 'Filed by Claude through the tracker’s tools.',
  manual: 'Typed into this panel.',
};

module.exports = {
  props: {
    id: { type: String, required: true },
  },

  data: function () {
    return {
      project: null,
      tasks: [],
      error: '',
      view: 'board',
      timer: null,
      // Which card is being carried, and where the line is currently drawn.
      // Not on the store: a drag belongs to this screen and ends with it.
      draggingId: null,
      dropStatus: null,
      dropIndex: 0,
      // Which cards have their detail open, keyed by id. Per screen rather than
      // stored: it is a glance at one card, not a preference.
      expanded: {},
      columns: COLUMNS,
    };
  },

  computed: {
    /* The cards split into their columns, in the order the server sent them -
       which is already the board's own order, so nothing is sorted here. Doing
       it in a computed rather than three filters in the template means the list
       is walked once per change instead of three times per render. */
    grouped: function () {
      var groups = { todo: [], queued: [], in_progress: [], done: [] };
      this.tasks.forEach(function (task) {
        if (groups[task.status]) groups[task.status].push(task);
      });
      return groups;
    },
  },

  mounted: function () {
    this.view = this.$readView(this.id);
    this.reload();
    this.$store.dispatch('settings');
    this.timer = setInterval(this.poll, this.$pollMs);
  },

  beforeDestroy: function () {
    if (this.timer) clearInterval(this.timer);
  },

  methods: {
    /* The polled read. It stops while a card is in the air.

       Replacing `tasks` mid-drag re-renders the column the pointer is over, and
       the elements the drop index was measured against are gone by the time the
       drop event arrives - the card lands somewhere nobody aimed it. Three
       seconds of a slightly stale board is the cheaper failure. */
    poll: function () {
      if (this.draggingId !== null) return;
      this.read(true);
    },

    reload: function () {
      this.read(false);
    },

    read: function (quiet) {
      var self = this;
      return axios.get('/api/projects/' + this.id).then(function (answer) {
        self.project = answer.data.project;
        self.tasks = answer.data.tasks;
        self.$store.commit('settings', answer.data.settings);
        self.error = '';
      }).catch(function (err) {
        // A failed poll says so once. A failed open says so and leaves the
        // screen empty, which is the honest rendering of "we do not know".
        self.error = self.$apiError(err);
        if (!quiet) self.tasks = [];
      });
    },

    setView: function (view) {
      this.view = view;
      this.$saveView(this.id, view);
    },

    sourceTitle: function (task) {
      return SOURCE_TITLES[task.source] || task.source;
    },

    toggle: function (task) {
      // Vue 2 cannot see a key added to an object after the fact.
      this.$set(this.expanded, task.id, !this.expanded[task.id]);
    },

    add: function () {
      this.$refs.editor.open({ projectId: Number(this.id) });
    },

    edit: function (task) {
      this.$refs.editor.open({ projectId: Number(this.id), task: task });
    },

    remove: async function (task) {
      var ok = await this.$refs.confirm.ask({
        title: 'DELETE TASK',
        body: 'Delete "' + task.title + '"?\n\nThis cannot be undone.',
        label: 'DELETE',
        danger: true,
      });
      if (!ok) return;
      var self = this;
      axios.delete('/api/tasks/' + task.id).then(function () {
        self.reload();
      }).catch(function (err) {
        self.error = self.$apiError(err);
      });
    },

    /* The table view's way of moving a card: to the foot of the column it
       picked, which is what the server does for a status change with no index.
       A select cannot express "third from the top" and should not try to. */
    pick: function (task, status) {
      if (status === task.status) return;
      var self = this;
      axios.patch('/api/tasks/' + task.id, { status: status }).then(function () {
        self.reload();
      }).catch(function (err) {
        self.error = self.$apiError(err);
        // The select is now showing a status the server did not accept. Reading
        // the board again is what puts the word back to what is true.
        self.reload();
      });
    },

    /* Drag and drop, with the browser's own events and no library.

       `setData` is not optional: Firefox refuses to start a drag at all without
       a payload on the transfer, and what is carried is the id as text so that
       a drop into anything else on the machine pastes something meaningful
       rather than nothing. The id this screen actually uses is the one on
       `draggingId` - reading it back from the transfer is only possible in the
       drop handler, and the line has to be drawn long before that. */
    start: function (event, task) {
      this.draggingId = task.id;
      if (event.dataTransfer) {
        event.dataTransfer.effectAllowed = 'move';
        try {
          event.dataTransfer.setData('text/plain', String(task.id));
        } catch (err) {
          // Some browsers refuse the call outside a real user gesture. The drag
          // still works; only a drop outside the panel loses its payload.
        }
      }
    },

    end: function () {
      this.draggingId = null;
      this.dropStatus = null;
    },

    /* Where the line goes: above the first card whose middle is below the
       pointer.

       Measured against the cards on screen rather than against their positions
       in the data, because that is what the operator is aiming at. The middle
       rather than the top edge, so the line flips at the point the pointer
       passes the halfway mark of a card instead of at the moment it touches
       it - the second reads as the line lagging behind the pointer. */
    over: function (event, status) {
      if (this.draggingId === null) return;
      if (event.dataTransfer) event.dataTransfer.dropEffect = 'move';
      var body = this.$refs['column-' + status];
      var host = Array.isArray(body) ? body[0] : body;
      if (!host) return;
      var cards = host.querySelectorAll('.tt-task');
      var where = cards.length;
      for (var i = 0; i < cards.length; i++) {
        var box = cards[i].getBoundingClientRect();
        if (event.clientY < box.top + box.height / 2) {
          where = i;
          break;
        }
      }
      this.dropStatus = status;
      this.dropIndex = where;
    },

    /* Leaving the column, but not leaving it for one of its own cards.

       `dragleave` fires every time the pointer crosses into a child element, so
       clearing on every one of them makes the line blink out over every card it
       passes. `relatedTarget` is where the pointer went; if that is still
       inside this column, nothing has been left. */
    leave: function (event, status) {
      var body = this.$refs['column-' + status];
      var host = Array.isArray(body) ? body[0] : body;
      var went = event.relatedTarget;
      if (host && went && host.contains(went)) return;
      if (this.dropStatus === status) this.dropStatus = null;
    },

    lineAt: function (status, slot) {
      return this.draggingId !== null && this.dropStatus === status && this.dropIndex === slot;
    },

    /* The drop, translated from what is on screen to what the server counts.

       The index measured above is over the cards as rendered, which includes
       the card being carried when it started in this column. The server places
       the card into the column with that card already taken out - so an index
       past its old slot is one too many, and without this correction every
       downward drag inside a column lands one place short. */
    drop: function (status) {
      var id = this.draggingId;
      this.draggingId = null;
      this.dropStatus = null;
      if (id === null) return;

      var column = this.grouped[status] || [];
      var from = -1;
      for (var i = 0; i < column.length; i++) {
        if (column[i].id === id) { from = i; break; }
      }
      var index = this.dropIndex;
      if (from !== -1) {
        if (index > from) index -= 1;
        if (index === from) return;
      }

      var self = this;
      axios.post('/api/tasks/' + id + '/move', { status: status, index: index })
        .then(function () { self.reload(); })
        .catch(function (err) {
          self.error = self.$apiError(err);
          self.reload();
        });
    },
  },
};
</script>
