<template>
  <div class="tt-page">
    <div class="tt-bar">
      <h1 class="tt-bar-title">PROJECTS</h1>
      <span class="tt-bar-gap"></span>
      <button type="button" class="btn btn-sm btn-primary" @click="refresh"
              title="Read the list again now">
        <i class="fa fa-rotate" aria-hidden="true"></i>
      </button>
    </div>

    <tt-alerts :error.sync="error"></tt-alerts>

    <div class="tt-card p-0">
      <table class="table table-striped table-hover mb-0">
        <thead>
          <tr>
            <th>PROJECT</th>
            <th style="width:180px">UPDATED</th>
            <th style="width:110px" class="text-end">QUEUED</th>
            <th style="width:60px"></th>
          </tr>
        </thead>
        <tbody>
          <!-- The whole row opens the board, and the name inside it is still a
               real link. The row is an enlargement of the target, not the only
               way in: a <tr> nobody can tab to would put this screen out of
               reach of the keyboard entirely. -->
          <tr v-for="project in projects" :key="project.id"
              class="tt-row-open" @click="open(project)">
            <td class="td-ellipsis">
              <router-link :to="'/projects/' + project.id" :title="project.path">
                {{ project.name }}
              </router-link>
            </td>
            <!-- "3 hours ago" in the cell, the exact stamp in the tooltip. The
                 question this column is read to answer is "what was I working
                 on", and a column of absolute stamps makes that a subtraction
                 done by eye on every row. -->
            <td :title="project.updated_at | datetime">{{ project.updated_at | ago }}</td>
            <td class="text-end">{{ project.queued }}</td>
            <td class="td-actions" @click.stop>
              <i class="fa fa-trash text-danger" role="button" tabindex="0"
                 title="Remove this project from the board"
                 @click="remove(project)" @keyup.enter="remove(project)"></i>
            </td>
          </tr>

          <!-- What an empty board says. Not "no data": the panel is empty on
               the day it is installed, and the one thing its owner needs to
               know then is that they do not have to do anything to fill it. -->
          <tr v-if="!projects.length && !error">
            <td colspan="4" class="text-center text-muted-soft py-3">
              No projects yet. One appears here the first time Claude writes a
              task while working in a directory.
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <tt-confirm ref="confirm"></tt-confirm>
  </div>
</template>

<script>
/* The first screen: every project, most recently touched first.

   It does not poll. The header does, into the same store, because the queued
   total in the bar is on every screen and one poll cannot disagree with itself.
   This screen dispatches once on mount so that opening the panel while the
   server is down says so immediately rather than after the first interval.
*/
module.exports = {
  data: function () {
    return { error: '' };
  },

  computed: {
    projects: function () {
      return this.$store.state.projects;
    },
  },

  watch: {
    /* The header's poll records why it failed; this screen is the one that has
       to say so. Copied into a local string rather than bound straight to the
       store so the operator can dismiss the bar - and so a recovered poll,
       which clears the recorded message, clears the bar with it. */
    '$store.state.projectsError': {
      immediate: true,
      handler: function (message) {
        this.error = message;
      },
    },
  },

  mounted: function () {
    this.refresh();
  },

  methods: {
    refresh: function () {
      this.$store.dispatch('projects').catch(function () {});
    },

    open: function (project) {
      this.$goto('/projects/' + project.id);
    },

    /* Removing a project removes its cards, which is why this asks first and
       says how many.

       "Remove from the board" rather than "delete": nothing on disk is touched
       and the project comes back by itself the next time Claude writes a task
       in that directory. The sentence says so, because a dialog that reads as
       though it might delete a repository is one nobody presses. */
    remove: async function (project) {
      var counted = project.queued + project.in_progress + project.done;
      var ok = await this.$refs.confirm.ask({
        title: 'REMOVE PROJECT',
        body: 'Remove "' + project.name + '" from the board?\n\n' +
              (counted
                ? 'Its ' + counted + ' visible ' + (counted === 1 ? 'task' : 'tasks') +
                  ' are deleted with it, along with any finished ones the board is ' +
                  'no longer drawing.\n\n'
                : '') +
              'Nothing in ' + project.path + ' is touched. The project reappears ' +
              'the next time Claude writes a task there.',
        label: 'REMOVE',
        danger: true,
      });
      if (!ok) return;
      var self = this;
      axios.delete('/api/projects/' + project.id).then(function () {
        self.$toast('success', 'Removed ' + project.name + ' from the board.');
        self.refresh();
      }).catch(function (err) {
        self.error = self.$apiError(err);
      });
    },
  },
};
</script>
