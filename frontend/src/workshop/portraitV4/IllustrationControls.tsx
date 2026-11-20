import {pages} from '../../gestures/surface';
import { useState } from 'react';
import { Choice } from '../../components/ui/choice';
import { proceduralPortrait } from '../proceduralPortrait';
import {
  illustrationCatalog as catalog,
  type Illustration,
  type Traits,
} from './illustration';
import { bodyFrames, type BodyFrame } from '../portraitAnatomy';

const groups = {
  face: ['face', 'eye_shape', 'brows', 'nose_shape', 'lip_shape'],
  hair: ['hair', 'facial_hair'],
  body: ['build'],
  clothes: ['clothing'],
  colors: ['skin', 'eyes', 'hair_color', 'clothing_color', 'trim'],
  details: ['detail', 'expression'],
} as const;
const names = {
  face: 'Форма лица',
  eye_shape: 'Глаза и веки',
  brows: 'Брови',
  nose_shape: 'Форма носа',
  lip_shape: 'Форма губ',
  hair: 'Причёска',
  facial_hair: 'Растительность на лице',
  build: 'Телосложение',
  clothing: 'Крой одежды',
  skin: 'Кожа',
  eyes: 'Радужка',
  hair_color: 'Волосы',
  clothing_color: 'Основная ткань',
  trim: 'Отделка',
  detail: 'Детали',
  expression: 'Мимика',
};
const sections = {
  face: 'Лицо',
  hair: 'Волосы',
  body: 'Тело и возраст',
  clothes: 'Одежда',
  colors: 'Цвета',
  details: 'Детали',
};
const ages = {
  infant: 'Младенец',
  child: 'Ребёнок',
  adolescent: 'Подросток',
  young_adult: 'Молодой взрослый',
  mature_adult: 'Зрелый взрослый',
  elderly: 'Пожилой',
};
export function IllustrationControls({
  value,
  onChange,
  eligible,
  ageReference,
  mode,
  setMode,
}: {
  value: Illustration;
  onChange: (p: Illustration) => void;
  eligible: boolean;
  ageReference?: { stage: string; visual_age?: Illustration['visual_age'] | null };
  mode: string;
  setMode: (id: 'auto' | 'procedural') => void;
}) {
  const [section, setSection] = useState<keyof typeof sections>('body'),
    [field, setField] = useState<keyof Traits>('face');
  const [query, search] = useState(''),
    [page, go] = useState(0);
  function select(key: keyof Traits) {
    setField(key);
    search('');
    go(0);
  }
  const styles = (field === 'trim' ? catalog.styles.clothing_color : catalog.styles[field]) as Record<
    string,
    string
  >;
  const choices = Object.entries(styles).filter(([, name]) =>
    name.toLocaleLowerCase('ru').includes(query.toLocaleLowerCase('ru')),
  );
  const colors = (catalog.colors as Record<string, Record<string, string>>)[
    field === 'trim' ? 'clothing_color' : field
  ];
  const compatible =
    field !== 'facial_hair' ||
    (eligible && !['infant', 'child', 'adolescent'].includes(value.visual_age || value.stage));
  const chosen = (key: keyof Traits, id: string): Illustration => ({
    ...value,
    form: 'human',
    traits: { ...value.traits, [key]: id },
  });
  function chooseTrait(key: keyof Traits, id: string) {
    onChange({ ...chosen(key, id), manual_traits: [...new Set([...(value.manual_traits || []), key])] });
  }
  const index = Math.min(page, Math.max(0, Math.ceil(choices.length / 8) - 1));
  function switchSection(s: keyof typeof sections) {
    setSection(s);
    select(groups[s][0]);
  }
  return (
    <>
      <div className="studio-section-choice">
        <Choice
          aria-label="Раздел настройки"
          value={section}
          onValueChange={(v) => switchSection(v as keyof typeof sections)}
        >
          {Object.entries(sections).map(([key, name]) => (
            <option key={key} value={key}>
              {name}
            </option>
          ))}
        </Choice>
      </div>
      <div {...pages(Object.keys(sections) as (keyof typeof sections)[],section,switchSection)} className="studio-tabs illustration-sections" role="group" aria-label="Раздел настройки">
        {(Object.keys(sections) as (keyof typeof sections)[]).map((s) => (
          <button type="button" key={s} aria-pressed={section === s} onClick={() => switchSection(s)}>
            {sections[s]}
          </button>
        ))}
      </div>
      <>
          {section === 'body' && (
            <>
              <label>
                Визуальный возраст
                <Choice
                  aria-label="Визуальный возраст"
                  value={value.visual_age_mode === 'auto' ? 'auto' : value.visual_age || 'auto'}
                  onValueChange={(id) => {
                    const age =
                      id === 'auto' ? ageReference?.visual_age || undefined : (id as keyof typeof ages);
                    onChange({
                      ...value,
                      visual_age: age,
                      visual_age_mode: id === 'auto' ? 'auto' : 'manual',
                      stage: id === 'auto' ? ageReference?.stage || value.stage : value.stage,
                      traits: {
                        ...value.traits,
                        ...(['infant', 'child', 'adolescent'].includes(age || value.stage)
                          ? { facial_hair: 'clean_shaven' as const }
                          : {}),
                      },
                    });
                  }}
                >
                  <option value="auto" disabled={!ageReference?.visual_age}>
                    По возрасту персонажа
                  </option>
                  {Object.entries(ages).map(([id, name]) => (
                    <option key={id} value={id}>
                      {name}
                    </option>
                  ))}
                </Choice>
              </label>
              <label>
                Основа тела
                <Choice
                  value={value.body_frame}
                  onValueChange={(id) => onChange({ ...value, body_frame: id as BodyFrame })}
                >
                  {Object.entries(bodyFrames).map(([id, name]) => (
                    <option key={id} value={id}>
                      {name}
                    </option>
                  ))}
                </Choice>
              </label>
            </>
          )}
          {section === 'details' && (
            <>
              <label>
                Вид изображения
                <Choice
                  value={value.form}
                  onValueChange={(id) =>
                    onChange({
                      ...value,
                      form: id as Illustration['form'],
                      traits: {
                        ...value.traits,
                        ...(id === 'neutral' ? { facial_hair: 'clean_shaven' as const } : {}),
                      },
                    })
                  }
                >
                  <option value="human">Человек</option>
                  <option value="neutral">Нейтральный силуэт</option>
                </Choice>
              </label>
              <label>
                Предпочтение
                <Choice value={mode} onValueChange={(id) => setMode(id as 'auto' | 'procedural')}>
                  <option value="auto">Фотография, если подходит</option>
                  <option value="procedural">Процедурная иллюстрация</option>
                </Choice>
              </label>
            </>
          )}
          <div {...pages(groups[section],field,select)} className="studio-tabs studio-subtabs">
            {groups[section].map((key) => (
              <button type="button" key={key} aria-pressed={key === field} onClick={() => select(key)}>
                {names[key]}
              </button>
            ))}
          </div>
          {!compatible ? (
            <p>
              Растительность на лице доступна взрослому персонажу с подходящей анатомией и взрослым
              визуальным возрастом.
            </p>
          ) : (
            <>
              {Object.keys(styles).length > 12 && (
                <input
                  type="search"
                  aria-label="Поиск вариантов"
                  placeholder="Найти вариант"
                  value={query}
                  onChange={(e) => {
                    search(e.target.value);
                    go(0);
                  }}
                />
              )}
              <p>
                {names[field]} · {styles[value.traits[field]]}
              </p>
              <div className={colors ? 'studio-colors' : 'studio-gallery'} aria-label={names[field]}>
                {choices.slice(index * 8, index * 8 + 8).map(([id, label]) => (
                  <button
                    type="button"
                    key={id}
                    aria-pressed={id === value.traits[field]}
                    onClick={() => chooseTrait(field, id)}
                  >
                    {colors ? (
                      <i style={{ backgroundColor: colors[id] }} />
                    ) : (
                      <span className={'studio-crop crop-' + field}>
                        <img
                          alt=""
                          decoding="async"
                          src={proceduralPortrait(chosen(field, id)) || undefined}
                        />
                      </span>
                    )}
                    <span>{label}</span>
                  </button>
                ))}
              </div>
              {!choices.length && <p>Вариантов не найдено.</p>}
              {choices.length > 8 && (
                <div className="studio-pages">
                  <button type="button" disabled={!index} onClick={() => go(index - 1)}>
                    Назад
                  </button>
                  <span>
                    {index + 1} / {Math.ceil(choices.length / 8)}
                  </span>
                  <button
                    type="button"
                    disabled={(index + 1) * 8 >= choices.length}
                    onClick={() => go(index + 1)}
                  >
                    Далее
                  </button>
                </div>
              )}
            </>
          )}
      </>
    </>
  );
}
