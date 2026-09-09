<template>
  <div class="tt-alerts" v-if="bars.length">
    <div v-for="bar in bars" :key="bar.kind"
         class="tt-alert" :class="'tt-alert-' + bar.kind" :role="bar.role">
      <i class="fa" :class="bar.icon" aria-hidden="true"></i>
      <span class="tt-alert-msg">{{ bar.text }}</span>
      <button type="button" class="btn-close" aria-label="Dismiss"
              @click="dismiss(bar.kind)"></button>
    </div>
  </div>
</template>

<script>
/* The four message bars every screen carries, above its content.

   Used as:

     <tt-alerts :error.sync="error" :info.sync="info"></tt-alerts>

   Four strings on the screen's own `data`, one component, and no screen
   deciding for itself where a failure goes or what colour it is.

   A toast is the other half of this and is not the same thing: a toast reports
   something that happened and goes away, a bar reports a state the screen is
   in and stays until it is not.
*/

/* The order, fixed here rather than by whichever string was set last. A bar
   that moves between renders is one the operator has to read again to find out
   which it is, and the one they are most likely to skip is the one saying the
   write failed.

   The role is the same decision for a screen reader: `alert` interrupts what is
   being spoken, `status` waits its turn. A failure is worth interrupting for; a
   save that worked is not. */
var BARS = [
  { kind: 'error',   icon: 'fa-circle-exclamation',   role: 'alert'  },
  { kind: 'warning', icon: 'fa-triangle-exclamation', role: 'alert'  },
  { kind: 'info',    icon: 'fa-circle-info',          role: 'status' },
  { kind: 'success', icon: 'fa-circle-check',         role: 'status' },
];

module.exports = {
  props: {
    error:   { type: String, default: '' },
    warning: { type: String, default: '' },
    info:    { type: String, default: '' },
    success: { type: String, default: '' },
  },
  computed: {
    /* Only the bars with something to say. A screen holding four empty strings
       renders nothing at all - not four empty boxes and not one collapsed
       container - so the content below sits in the same place whether or not
       the last write had anything to report. */
    bars: function () {
      var self = this;
      return BARS.filter(function (bar) {
        return !!self[bar.kind];
      }).map(function (bar) {
        return { kind: bar.kind, icon: bar.icon, role: bar.role, text: self[bar.kind] };
      });
    },
  },
  methods: {
    /* `.sync` on the parent turns this into `error = ''`, so the string stays
       the screen's to own and this component never writes a prop of its own. */
    dismiss: function (kind) {
      this.$emit('update:' + kind, '');
    },
  },
};
</script>
