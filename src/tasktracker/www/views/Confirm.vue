<template>
  <div class="modal fade" ref="modalEl" tabindex="-1" aria-hidden="true">
    <div class="modal-dialog">
      <div class="modal-content">

        <div class="modal-header bg-blue py-1 px-3">
          <h5 class="modal-title font-weight-bold mb-0">{{ title }}</h5>
          <button type="button" class="btn btn-primary btn-sm"
                  data-bs-dismiss="modal" aria-label="Close">
            <i class="fa fa-times"></i>
          </button>
        </div>

        <!-- `pre-line`, so a question with two paragraphs is read as two. The
             body is plain text bound as text - it can never be markup - and
             without this a caller's blank line collapses into a space and the
             warning runs into the question it qualifies. -->
        <div class="modal-body py-2" style="white-space:pre-line">{{ body }}</div>

        <div class="modal-footer p-1 d-flex justify-content-end">
          <button type="button" ref="cancelEl"
                  class="btn btn-sm btn-secondary fw-bold" style="min-width:100px"
                  data-bs-dismiss="modal">CANCEL</button>
          <button type="button" class="btn btn-sm fw-bold" style="min-width:100px"
                  :class="danger ? 'btn-danger' : 'btn-primary'"
                  @click="confirm">{{ label }}</button>
        </div>

      </div>
    </div>
  </div>
</template>

<script>
/* The one question this panel is allowed to ask before it destroys something.

   The browser's own confirm dialog is what this replaces. Two reasons beyond
   the look of it: it is drawn by the browser, so it names the page's origin
   rather than the card about to be deleted; and it blocks the whole event loop,
   so the board's poll piles up behind it while it is open.

   Used as:

     <tt-confirm ref="confirm"></tt-confirm>

     var ok = await this.$refs.confirm.ask({
       title: 'DELETE TASK',
       body: 'Delete "write the patch"? This cannot be undone.',
       label: 'DELETE',
       danger: true,
     });
     if (!ok) return;

   `ask()` resolves true only when the confirming button was pressed. Every
   other way out - the x, Cancel, Esc, a click on the backdrop, the route
   changing under it - resolves false. Never nothing: a promise left pending is
   a delete that silently does nothing, on a screen whose buttons stay disabled
   waiting for an answer that is not coming.

   Moving a card between columns does NOT come here. That is one drag, it is
   reversible by dragging back, and a dialog in front of it would be a question
   with no wrong answer.
*/
module.exports = {
  data: function () {
    return {
      title:  'CONFIRM',
      body:   '',
      label:  'CONFIRM',
      danger: false,
    };
  },

  mounted: function () {
    // The Bootstrap handle is deliberately kept off `data`: Vue would make the
    // library object reactive and walk every field it owns.
    this.modalEl = this.$refs.modalEl;
    this.modal = new bootstrap.Modal(this.modalEl);
    // Not reactive state either - these only carry one answer from the click
    // that produced it to the `hidden` event that reports it.
    this.settle = null;
    this.answer = false;
    this.modalEl.addEventListener('hidden.bs.modal', this.handleHidden);
    this.modalEl.addEventListener('shown.bs.modal', this.handleShown);
  },

  /* Vue 2 spelling. A dialog left open when the route changes takes its
     backdrop with it - Bootstrap appends that to <body>, outside this
     component's subtree - and the next screen renders under a grey sheet it
     cannot dismiss, on a <body> still carrying `overflow: hidden`. */
  beforeDestroy: function () {
    if (this.modalEl) {
      this.modalEl.removeEventListener('hidden.bs.modal', this.handleHidden);
      this.modalEl.removeEventListener('shown.bs.modal', this.handleShown);
    }
    // Before dispose, or the `hidden` event that would have settled it never
    // arrives and the caller waits forever on a component that no longer
    // exists.
    this.finish(false);
    if (this.modal) {
      this.modal.dispose();
      this.modal = null;
    }
    this.modalEl = null;
  },

  methods: {
    ask: function (options) {
      var self = this;
      var opts = options || {};
      // A second ask() while one is open answers the first caller "no" rather
      // than leaving it behind a dialog it no longer owns.
      this.finish(false);
      this.title  = opts.title || 'CONFIRM';
      this.body   = opts.body  || '';
      this.label  = opts.label || 'CONFIRM';
      this.danger = !!opts.danger;
      this.answer = false;
      // No modal means no way to ask, and the safe answer to a question that
      // was never put is no.
      if (!this.modal) return Promise.resolve(false);
      return new Promise(function (resolve) {
        self.settle = resolve;
        self.modal.show();
      });
    },

    /* Recorded here, reported from `hidden`. Resolving on the click instead
       lets the caller open its own dialog - the key editor, the reissue box -
       while this one is still fading out, which leaves Bootstrap with two
       backdrops and only one of them removable. */
    confirm: function () {
      this.answer = true;
      if (this.modal) this.modal.hide();
      else this.finish(true);
    },

    handleHidden: function () {
      this.finish(this.answer);
    },

    /* Focus lands on Cancel, not on the confirming button. Bootstrap focuses
       the dialog itself and leaves Enter doing nothing, which is safe but
       leaves the keyboard a tab away from an answer; starting on Cancel gives
       Enter a meaning, and the meaning it gets is the one that destroys
       nothing. */
    handleShown: function () {
      if (this.$refs.cancelEl) this.$refs.cancelEl.focus();
    },

    /* Settle the outstanding promise exactly once. Every way out of the dialog
       ends here, and `settle` is cleared before it is called so a second path
       out - hide() followed by dispose(), say - cannot resolve it twice. */
    finish: function (value) {
      var settle = this.settle;
      this.settle = null;
      this.answer = false;
      if (settle) settle(!!value);
    },
  },
};
</script>
