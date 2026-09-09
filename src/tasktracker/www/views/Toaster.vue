<template>
  <div class="tt-toaster" aria-live="polite">
    <div v-for="toast in $store.state.toasts" :key="toast.id"
         class="tt-toast" :class="'tt-toast-' + toast.kind"
         @click="dismiss(toast.id)">
      <span class="tt-toast-msg">{{ toast.text }}</span>
      <i class="fa fa-xmark" aria-hidden="true"></i>
    </div>
  </div>
</template>

<script>
/* Every toast on the panel, in one fixed corner.

   Each is dismissed on click and, failing that, on a timer. The timer is here
   rather than in `$toast` so a toast that is never rendered - the store
   mutating while the panel is being torn down - cannot leave a pending timeout
   behind it.

   Six seconds: long enough to read two lines, short enough that three failures
   in a row do not stack into a wall over the board. */
var LIFE_MS = 6000;

module.exports = {
  data: function () {
    return { timers: {} };
  },
  watch: {
    '$store.state.toasts': {
      immediate: true,
      handler: function (toasts) {
        var self = this;
        toasts.forEach(function (toast) {
          if (self.timers[toast.id]) return;
          self.timers[toast.id] = setTimeout(function () {
            self.dismiss(toast.id);
          }, LIFE_MS);
        });
      },
    },
  },
  methods: {
    dismiss: function (id) {
      if (this.timers[id]) {
        clearTimeout(this.timers[id]);
        delete this.timers[id];
      }
      this.$store.commit('dismiss', id);
    },
  },
  beforeDestroy: function () {
    var self = this;
    Object.keys(this.timers).forEach(function (id) { clearTimeout(self.timers[id]); });
  },
};
</script>
