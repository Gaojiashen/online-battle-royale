// player_modules.js — Player Panel 模块注册表
// 新增模块只需在此注册。enter/exit 函数名对应全局作用域中的函数。
const PlayerModules = [
  {
    id: 'battle',
    icon: '&#9876;',
    name: '战斗',
    desc: '当前对战与历史回顾',
    enabled: true,
    enter: 'enterBattleModule',
    exit: 'exitBattleModule'
  },
  {
    id: 'inventory',
    icon: '&#127890;',
    name: '背包',
    desc: '暂未开放',
    enabled: false,
    enter: null,
    exit: null
  },
  {
    id: 'achievement',
    icon: '&#127942;',
    name: '成就',
    desc: '暂未开放',
    enabled: false,
    enter: null,
    exit: null
  }
];
