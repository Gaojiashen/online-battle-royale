// module_manager.js — Player Module Lifecycle Manager
const ModuleManager = {
  _currentId: null,

  open(moduleId, btn) {
    const mod = PlayerModules.find(m => m.id === moduleId);
    if (!mod || !mod.enabled) return;

    // Exit current module
    if (this._currentId) {
      this._exit(this._currentId);
    }

    // Enter target module
    this._currentId = moduleId;
    if (mod.enter && typeof window[mod.enter] === 'function') {
      window[mod.enter](btn);
    }
  },

  close(moduleId) {
    this._exit(moduleId);
    if (this._currentId === moduleId) {
      this._currentId = null;
    }
  },

  _exit(moduleId) {
    const mod = PlayerModules.find(m => m.id === moduleId);
    if (mod && mod.exit && typeof window[mod.exit] === 'function') {
      window[mod.exit]();
    }
  },

  current() {
    return this._currentId;
  }
};
