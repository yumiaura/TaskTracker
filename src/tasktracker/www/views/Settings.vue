<template>
  <div class="tt-page">
    <div class="tt-bar">
      <h1 class="tt-bar-title">SETTINGS</h1>
    </div>

    <tt-alerts :error.sync="error" :success.sync="success"></tt-alerts>

    <div class="tt-card">
      <div class="tt-settings-grid">
        <label for="tt-hide-days">HIDE FINISHED TASKS AFTER</label>
        <div class="input-group input-group-sm">
          <input id="tt-hide-days" type="number" min="0" max="3650" step="1"
                 class="form-control form-control-sm" v-model.number="days" />
          <span class="input-group-text">days</span>
        </div>

      </div>

      <!-- What the number does, and what it does not do. The second half is the
           important half: "hide" is a word people read as "delete", and
           somebody who thinks this throws work away will set it to the largest
           number the field accepts and never touch it again.

           Outside the grid above, because an item spanning both of its columns
           sizes them - and this paragraph would make the label column as wide
           as itself. -->
      <p class="tt-settings-note mb-0 mt-2">
        A task stays on the board for this long after it is finished, then stops
        being drawn. It is never deleted - raise the number and the cards come
        back. <strong>0</strong> keeps every finished task on the board for good.
      </p>

      <div class="mt-3">
        <button type="button" class="btn btn-sm btn-primary fw-bold" style="min-width:100px"
                :disabled="!changed || saving" @click="save">SAVE</button>
      </div>
    </div>

    <div class="tt-card mt-2">
      <h3 class="mb-2">ABOUT THIS BOARD</h3>
      <div class="tt-settings-grid">
        <label>DATABASE</label>
        <span class="tt-path" :title="database">{{ database || '…' }}</span>
      </div>
      <p class="tt-settings-note mb-0 mt-2">
        One SQLite file for every project. Claude Code and Codex write to it
        through the tracker's MCP tools and hooks that mirror their plans;
        this panel reads and writes the same rows.
      </p>
    </div>
  </div>
</template>

<script>
/* The one setting the server owns, and where its data lives.

   It is on the server rather than in this browser precisely because it decides
   what the API sends: the cutoff is applied in the query that chooses the
   cards, so a second window - or Claude asking through MCP - sees the same
   board. A per-browser answer would mean two windows disagreeing about how much
   work had been done this week.

   The theme and the board/table choice go the other way and live in
   localStorage: they are about the screen you are sitting at.
*/
module.exports = {
  data: function () {
    return {
      days: null,
      saved: null,
      database: '',
      error: '',
      success: '',
      saving: false,
    };
  },

  computed: {
    /* SAVE is live only when there is something to save. A button that is
       always enabled invites a press that writes what is already there, and
       then reports success for having done nothing. */
    changed: function () {
      return this.days !== this.saved && this.valid;
    },
    valid: function () {
      return typeof this.days === 'number' && isFinite(this.days) &&
             this.days >= 0 && this.days <= 3650;
    },
  },

  mounted: function () {
    var self = this;
    this.$store.dispatch('settings').then(function (settings) {
      if (!settings) {
        self.error = 'The settings could not be read.';
        return;
      }
      self.days = settings.done_hide_days;
      self.saved = settings.done_hide_days;
    });
    axios.get('/api/health').then(function (answer) {
      self.database = answer.data.database;
    }).catch(function () {
      // The path is a nicety on a screen whose actual job is the field above.
      // A board that refused to render its one setting because it could not
      // name its own file would be reporting the wrong failure.
    });
  },

  methods: {
    save: function () {
      if (!this.changed || this.saving) return;
      var self = this;
      this.saving = true;
      axios.put('/api/settings', { done_hide_days: this.days }).then(function (answer) {
        self.$store.commit('settings', answer.data);
        self.saved = answer.data.done_hide_days;
        self.days = answer.data.done_hide_days;
        self.error = '';
        self.success = self.saved === 0
          ? 'Finished tasks now stay on the board for good.'
          : 'Finished tasks are hidden ' + self.saved +
            (self.saved === 1 ? ' day' : ' days') + ' after they are done.';
      }).catch(function (err) {
        self.success = '';
        self.error = self.$apiError(err);
      }).then(function () {
        self.saving = false;
      });
    },
  },
};
</script>
