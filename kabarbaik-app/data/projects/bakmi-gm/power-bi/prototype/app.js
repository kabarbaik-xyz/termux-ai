/* Bakmi GM BI Dashboard — prototype interactivity */
const App = {
  state: {
    currentScreen: 'login',
    loading: false,
    filters: {},
    drill: {}
  },
  init() {
    document.querySelectorAll('[data-nav]').forEach(el => {
      el.addEventListener('click', (e) => {
        const target = e.currentTarget.dataset.nav;
        this.go(target);
      });
    });
    document.querySelectorAll('[data-toggle-state]').forEach(el => {
      el.addEventListener('click', (e) => {
        const state = e.currentTarget.dataset.toggleState;
        this.toggleState(state);
      });
    });
    document.querySelectorAll('[data-tab]').forEach(el => {
      el.addEventListener('click', (e) => {
        const tab = e.currentTarget.dataset.tab;
        this.switchTab(tab);
      });
    });
  },
  go(screen) {
    this.state.currentScreen = screen;
    window.location.hash = screen;
  },
  toggleState(state) {
    const map = { loading: 'state-loading', empty: 'state-empty', error: 'state-error', noperm: 'state-noperm', populated: 'state-populated' };
    document.querySelectorAll('[class*="state-"]').forEach(el => el.classList.remove('active'));
    const target = document.getElementById(map[state]);
    if (target) target.classList.add('active');
  },
  switchTab(tab) {
    const parent = document.querySelector('.tabs');
    if (!parent) return;
    parent.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
    document.querySelectorAll('[data-panel]').forEach(p => p.style.display = p.dataset.panel === tab ? '' : 'none');
  },
  simulateLoading(callback, ms = 800) {
    this.toggleState('loading');
    setTimeout(() => {
      this.toggleState('populated');
      if (callback) callback();
    }, ms);
  }
};

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => App.init());
} else {
  App.init();
}
