// state.js — Player Panel 全局状态（唯一真相源）
const PlayerState = {
  playerName: '',
  currentBattleId: '',
  mySide: '',
  currentState: '',
  pollTimer: null,
  availableCardsData: [],
  selectedCards: [],

  reset() {
    this.currentBattleId = '';
    this.mySide = '';
    this.currentState = '';
    this.availableCardsData = [];
    this.selectedCards = [];
    this.pollTimer = null;
  },

  setPlayer(name) {
    this.playerName = name;
  },

  setBattle(bid) {
    this.currentBattleId = bid;
  },

  clearBattle() {
    this.currentBattleId = '';
    this.pollTimer = null;
  }
};
