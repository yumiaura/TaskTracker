<template>
  <div class="modal fade" ref="modalEl" tabindex="-1" aria-hidden="true">
    <div class="modal-dialog">
      <div class="modal-content">

        <div class="modal-header bg-blue py-1 px-3">
          <h5 class="modal-title font-weight-bold mb-0">{{ heading }}</h5>
          <button type="button" class="btn btn-primary btn-sm"
                  data-bs-dismiss="modal" aria-label="Close">
            <i class="fa fa-times"></i>
          </button>
        </div>

        <!-- A real form, so Enter in the title field saves rather than doing
             nothing. `@submit.prevent` because there is nowhere to post to. -->
        <form class="modal-body py-2" @submit.prevent="save">
          <div class="mb-2">
            <label class="form-label mb-1" for="tt-task-title">TITLE</label>
            <input id="tt-task-title" ref="titleEl" v-model="title"
                   class="form-control form-control-sm" maxlength="200"
                   placeholder="What has to happen" />
          </div>

          <div class="mb-2">
            <label class="form-label mb-1" for="tt-task-detail">DETAIL</label>
            <!-- Where a paste of four paragraphs goes. The card draws the title
                 on one line and this behind a glyph, which is the whole reason
                 the two are separate fields rather than one growing box. -->
            <textarea id="tt-task-detail" v-model="detail" rows="5"
                      class="form-control form-control-sm"
                      placeholder="Anything the title cannot hold - notes, a link, the reason"></textarea>
          </div>

          <div>
            <label class="form-label mb-1" for="tt-task-status">STATUS</label>
            <select id="tt-task-status" v-model="status" class="form-select form-select-sm">
              <option value="queued">QUEUE</option>
              <option value="in_progress">IN PROGRESS</option>
              <option value="done">DONE</option>
            </select>
          </div>
          <div class="mt-2" v-if="mergeHistory.length">
            <details v-for="(entry, index) in mergeHistory" :key="index" class="mb-2">
              <summary>MERGED CARDS</summary>
              <p class="small my-1">{{ entry.reason }}</p>
              <div v-for="original in entry.originals" :key="original.id" class="small mb-2">
                <strong>{{ original.source.toUpperCase() }} #{{ original.id }}: {{ original.title }}</strong>
                <div style="white-space:pre-wrap;overflow-wrap:anywhere">{{ original.detail }}</div>
              </div>
            </details>
          </div>
        </form>

        <div class="modal-footer p-1 d-flex justify-content-end">
          <!-- On the left, away from SAVE, and only for a task that exists. It
               does not delete by itself: it closes this dialog and hands the task
               to the screen, which asks first, as the trash icon does. -->
          <button type="button" class="btn btn-sm btn-outline-danger fw-bold me-auto"
                  style="min-width:100px" v-if="taskId !== null" @click="askRemove">DELETE</button>
          <button type="button" class="btn btn-sm btn-secondary fw-bold" style="min-width:100px"
                  data-bs-dismiss="modal">CANCEL</button>
          <button type="button" class="btn btn-sm btn-primary fw-bold" style="min-width:100px"
                  :disabled="!title.trim() || saving" @click="save">SAVE</button>
        </div>

      </div>
    </div>
  </div>
</template>

<script>
/* The one editor both views of a board open.

   Used as:

     <tt-task-dialog ref="editor" @saved="reload" @remove="remove"></tt-task-dialog>

     this.$refs.editor.open({ projectId: 4 });            // a new card
     this.$refs.editor.open({ projectId: 4, task: row }); // an existing one

   It reports two things. `saved`, after which the screen that opened it re-reads
   the board - which is also what a poll would have done, so there is one path
   by which cards get onto the screen rather than two that can disagree. And
   `remove` with the task, when DELETE is pressed: sent after the dialog has
   finished closing, so the screen's confirmation opens on a page with no second
   dialog still fading out under it.

   A card being edited here is NOT locked against the poll behind it. The dialog
   holds its own copy of the fields; a save writes the fields the operator
   touched and leaves the rest, so a status Claude changed in the meantime
   survives an edit of the title.
*/
module.exports = {
  data: function () {
    return {
      projectId: null,
      taskId: null,
      task: null,
      title: '',
      detail: '',
      status: 'queued',
      saving: false,
      mergeHistory: [],
    };
  },

  computed: {
    heading: function () {
      return this.taskId === null ? 'NEW TASK' : 'EDIT TASK';
    },
  },

  mounted: function () {
    // The Bootstrap handle is deliberately kept off `data`: Vue would make the
    // library object reactive and walk every field it owns.
    this.modalEl = this.$refs.modalEl;
    this.modal = new bootstrap.Modal(this.modalEl);
    this.modalEl.addEventListener('shown.bs.modal', this.handleShown);
  },

  /* A dialog left open when the route changes takes its backdrop with it -
     Bootstrap appends that to <body>, outside this component's subtree - and
     the next screen renders under a grey sheet it cannot dismiss, on a <body>
     still carrying `overflow: hidden`. */
  beforeDestroy: function () {
    if (this.modalEl) {
      this.modalEl.removeEventListener('shown.bs.modal', this.handleShown);
    }
    if (this.modal) {
      this.modal.hide();
      this.modal.dispose();
      this.modal = null;
    }
    this.modalEl = null;
  },

  methods: {
    open: function (options) {
      var opts = options || {};
      var task = opts.task || null;
      this.projectId = opts.projectId;
      this.taskId = task ? task.id : null;
      this.task = task;
      this.title = task ? task.title : '';
      this.detail = task ? (task.detail || '') : '';
      this.status = task ? task.status : 'queued';
      this.saving = false;
      this.mergeHistory = [];
      if (task && task.sources) {
        var self = this;
        axios.get('/api/tasks/' + task.id).then(function (response) {
          if (self.taskId === task.id) self.mergeHistory = response.data.merge_history;
        }).catch(function (err) {
          self.$toast('danger', self.$apiError(err));
        });
      }
      if (this.modal) this.modal.show();
    },

    /* Focus lands in the title field, which is the only field a new card needs
       and the field an edit almost always starts in. Bootstrap focuses the
       dialog itself and leaves the first keystroke going nowhere. */
    handleShown: function () {
      if (this.$refs.titleEl) this.$refs.titleEl.focus();
    },

    askRemove: function () {
      var self = this;
      var task = this.task;
      if (!task || !this.modal) return;
      this.modalEl.addEventListener('hidden.bs.modal', function closed() {
        self.modalEl.removeEventListener('hidden.bs.modal', closed);
        self.$emit('remove', task);
      });
      this.modal.hide();
    },

    save: function () {
      var clean = this.title.trim();
      if (!clean || this.saving) return;
      var self = this;
      this.saving = true;

      var sent = this.taskId === null
        ? axios.post('/api/projects/' + this.projectId + '/tasks',
                     { title: clean, detail: this.detail, status: this.status })
        : axios.patch('/api/tasks/' + this.taskId,
                      { title: clean, detail: this.detail, status: this.status });

      sent.then(function () {
        if (self.modal) self.modal.hide();
        self.$emit('saved');
      }).catch(function (err) {
        // Reported as a toast rather than into a bar inside the dialog: the
        // dialog stays open with what was typed still in it, and a bar added
        // above the fields would push the buttons off a short window.
        self.$toast('danger', self.$apiError(err));
      }).then(function () {
        self.saving = false;
      });
    },
  },
};
</script>
