export const tr = (ru: string, en: string) =>
  document.documentElement.lang.startsWith('en') ? en : ru;
