/** Base geometry + independent decoration + accent. Presets are only compositions. */
export const themes=[
 {id:'graphite',name:'Graphite',description:'Чистые панели · современная типографика',base:'modern',decoration:'none',accent:'#dbb980',bg:'#141619',surface:'#1b1e22',text:'#ecebe6'},
 {id:'cyberpunk',name:'Cyberpunk',description:'HUD · неоновые направляющие · сетка',base:'hud',decoration:'cyberpunk',accent:'#6edde0',bg:'#09131c',surface:'#12212c',text:'#e4f3f8'},
 {id:'industrial',name:'Industrial',description:'Металлические панели · болты · маркировка',base:'metal',decoration:'industrial',accent:'#e7be68',bg:'#171a1c',surface:'#242a2d',text:'#e8e8e1'},
 {id:'medieval',name:'Medieval',description:'Дерево · железные накладки · гербы',base:'wood',decoration:'medieval',accent:'#d9b783',bg:'#1d1712',surface:'#2c231b',text:'#eee1c9'},
 {id:'arcane',name:'Arcane',description:'Руны · магические окружности · свечение',base:'ornate',decoration:'arcane',accent:'#c7a6f5',bg:'#181322',surface:'#261e35',text:'#eee5fa'},
 {id:'parchment',name:'Parchment',description:'Пергамент · чернила · книжные разделители',base:'paper',decoration:'parchment',accent:'#785128',bg:'#f2e9d7',surface:'#f9f2e4',text:'#30291f'},
 {id:'gothic',name:'Gothic',description:'Стрельчатые арки · бордовый бархат',base:'ornate',decoration:'gothic',accent:'#e299b4',bg:'#151014',surface:'#21171f',text:'#f0e6e6'},
 {id:'urban',name:'Urban',description:'Бетон · стекло · линии городского транспорта',base:'modern',decoration:'urban',accent:'#94c4cd',bg:'#172023',surface:'#253136',text:'#eaf1ee'},
 {id:'street',name:'Street',description:'Рваные афиши · скотч · маркер',base:'poster',decoration:'street',accent:'#e1e88a',bg:'#1c1b1d',surface:'#2d2b31',text:'#f5f2e9'},
 {id:'noir',name:'Noir',description:'Монохромное досье · штампы · жалюзи',base:'dossier',decoration:'noir',accent:'#d2d2d2',bg:'#141414',surface:'#242424',text:'#f0f0f0'},
 {id:'terminal',name:'Terminal',description:'Моноширинный терминал · CRT',base:'terminal',decoration:'terminal',accent:'#9ae6ab',bg:'#07150e',surface:'#10241a',text:'#d3eed7'},
 {id:'space',name:'Space',description:'Корабельные панели · координаты · приборы',base:'hud',decoration:'space',accent:'#94bdf4',bg:'#101827',surface:'#1b293d',text:'#e5edf8'},
 {id:'post-apocalypse',name:'Post-Apocalypse',description:'Ржавчина · ремонтные швы · аналоговые шкалы',base:'metal',decoration:'post-apocalypse',accent:'#d8aa78',bg:'#211c17',surface:'#332b21',text:'#ede3cc'},
 {id:'biotech',name:'Biotech',description:'Органические линии · клеточные структуры',base:'organic',decoration:'biotech',accent:'#8fd9c7',bg:'#102022',surface:'#1c3335',text:'#def3ed'},
 {id:'occult',name:'Occult',description:'Ритуальные схемы · рукописные заметки',base:'dossier',decoration:'occult',accent:'#d1a0a5',bg:'#1d1319',surface:'#2c2028',text:'#eddee2'},
 {id:'retro',name:'Retro',description:'Аналоговые приборы · старые дисплеи',base:'retro',decoration:'retro',accent:'#efbf7b',bg:'#28221e',surface:'#3a3028',text:'#f9ebd6'},
 // Preserve saved Neon worlds as an alias composition.
 {id:'neon',name:'Neon',description:'Классический неон · HUD',base:'hud',decoration:'cyberpunk',accent:'#6edde0',bg:'#0c1420',surface:'#131f2d',text:'#e4f3f8'},
] as const;
export type ThemeId=typeof themes[number]['id'];
export type SkinComposition={base:string;decoration:string;accent:string};
