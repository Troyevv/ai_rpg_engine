// Presentation labels follow the project's lib/social.ts boundary.
const domains:Record<string,string>={social_contact:'новые знакомства',training:'обучение',employment:'работа или подработка',relationship:'развитие отношений',relocation:'переезд или совместное проживание'};
export const advanceDomainLabel=(value:string)=>domains[value]||'возможность';
