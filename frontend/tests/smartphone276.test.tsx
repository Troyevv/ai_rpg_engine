import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { expect, it, vi } from 'vitest';
import { Newspaper } from 'lucide-react';
import { Phone } from '../src/Phone';
import { apps, type PhoneApp } from '../src/phone/registry';
import { useDevice } from '../src/phone/usePhone';
import type { Save, ModelConfig } from '../src/types';

function News() {
  const d = useDevice();
  return d.route ? <h3>Статья</h3> : <button onClick={() => d.push('article')}>Открыть статью</button>;
}
const news: PhoneApp = {
  id: 'test-news',
  title: 'Новости',
  icon: Newspaper,
  screen: News,
  available: (c) => !!c.social,
};

it('opens a test-only app through the registry and shares its navigation and capability boundary', async () => {
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      disconnect() {}
    },
  );
  const host = document.createElement('div');
  host.id = 'root';
  document.body.appendChild(host);
  const root = createRoot(host);
  const save = {
    id: 276,
    turns: [],
    revision: 1,
    state: {
      characters: [],
      phone: {
        actor_id: 'a',
        capabilities: { social: true, text_message: true },
        contacts: [],
        conversations: [],
        events: [],
        emergency: [],
        badges: { 'test-news': 105 },
      },
    },
  } as unknown as Save;
  const render = (s: Save) =>
    act(() =>
      root.render(
        <Phone
          save={s}
          registry={[...apps, news]}
          config={{} as ModelConfig}
          apiKey=""
          job={null}
          disabled={false}
          onJob={() => {}}
          onCommit={() => {}}
          onBusyChange={() => {}}
          openCharacter={() => {}}
        />,
      ),
    );
  const click = async (selector: string) => {
    const el = host.querySelector<HTMLButtonElement>(selector);
    expect(el).toBeTruthy();
    await act(() => el!.click());
  };
  try {
    await render(save);
    await click('.phone-peek');
    expect(host.querySelector('[data-app=test-news]')?.textContent).toContain('99+');
    await click('[data-app=test-news]');
    await click('.phone-body button');
    expect(host.querySelector('h3')?.textContent).toBe('Статья');
    await act(() => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })));
    expect(host.querySelector('.phone-body')?.textContent).toContain('Открыть статью');
    await click('[aria-label=Домой]');
    await click('[data-app=test-news]');
    await click('.ph-close');
    expect(host.querySelector('.phone-peek')?.getAttribute('aria-expanded')).toBe('false');
    await click('.phone-peek');
    await click('[data-app=test-news]');
    await click('.phone-body button');
    const other = structuredClone(save);
    other.state.phone!.actor_id = 'b';
    other.state.phone!.capabilities.social = false;
    await render(other);
    await click('.phone-peek');
    expect(host.querySelector('[data-app=test-news]')).toBeNull();
    expect(host.querySelector('.phone-body')?.textContent).not.toContain('Статья');
    expect(apps.some((app) => app.id === 'test-news')).toBe(false);
  } finally {
    await act(() => root.unmount());
    host.remove();
    vi.unstubAllGlobals();
  }
});

it('opens a canonical conversation referenced by a detail ahead of the launcher snapshot', async () => {
  const { usePhone } = await import('../src/phone/usePhone');
  const initial = {
    id: 277,
    revision: 4,
    turns: [],
    state: {
      characters: [],
      phone: {
        actor_id: 'owner',
        capabilities: { social: true, text_message: true },
        contacts: [],
        recipients: [],
        conversations: [],
        events: [],
        emergency: [],
        badges: {},
      },
    },
  } as unknown as Save;
  const next = { ...initial, revision: 5 };
  const commit = vi.fn();
  const fetcher = vi.fn(async () => new Response(JSON.stringify(next)));
  vi.stubGlobal('fetch', fetcher);
  const host = document.createElement('div');
  const root = createRoot(host);
  function Harness() {
    const d = usePhone(
      {
        save: initial,
        config: {} as ModelConfig,
        apiKey: '',
        job: null,
        disabled: false,
        onJob: () => {},
        onCommit: commit,
        onBusyChange: () => {},
        openCharacter: () => {},
      },
      '277:owner',
    );
    return (
      <button onClick={() => void d.openChat('employer-thread')}>
        {d.tab}/{d.conversation}
      </button>
    );
  }
  try {
    await act(() => root.render(<Harness />));
    await act(() => host.querySelector('button')!.click());
    expect(host.textContent).toBe('messages/employer-thread');
    expect(fetcher).toHaveBeenCalledWith('/api/saves/277', expect.objectContaining({ method: 'GET' }));
    expect(commit).toHaveBeenCalledWith(next);
  } finally {
    await act(() => root.unmount());
    vi.unstubAllGlobals();
  }
});

it('submits a foreground action behind an in-flight Knowledge receipt without losing the click', async () => {
  const { usePhone } = await import('../src/phone/usePhone');
  const initial = {
    id: 278,
    revision: 4,
    turns: [],
    state: {
      characters: [],
      phone: {
        actor_id: 'owner',
        capabilities: { text_message: true, social: true },
        contacts: [],
        recipients: [],
        conversations: [],
        events: [],
        emergency: [],
        badges: {},
      },
    },
  } as unknown as Save;
  let release!: (response: Response) => void;
  const receipt = new Promise<Response>((resolve) => {
    release = resolve;
  });
  const payloads: { revision: number; command: { action: string } }[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_url, options) => {
      const payload = JSON.parse(options.body);
      payloads.push(payload);
      return payload.command.action === 'read'
        ? receipt
        : new Response(JSON.stringify({ ...initial, revision: 6 }));
    }),
  );
  let device!: ReturnType<typeof usePhone>;
  function Harness() {
    device = usePhone(
      {
        save: initial,
        config: {} as ModelConfig,
        apiKey: '',
        job: null,
        disabled: false,
        onJob: () => {},
        onCommit: () => {},
        onBusyChange: () => {},
        openCharacter: () => {},
      },
      '278:owner',
    );
    return null;
  }
  const root = createRoot(document.createElement('div'));
  try {
    await act(() => root.render(<Harness />));
    await act(() => device.observe('news', ['article']));
    await vi.waitFor(() => expect(payloads.map((p) => p.command.action)).toEqual(['read']));
    expect(device.locked).toBe(false);
    let submitted!: Promise<boolean>;
    act(() => {
      submitted = device.command('questions', 'ask', { target: 'recipient', text: 'Как дела?' });
    });
    await act(async () => {
      release(new Response(JSON.stringify({ ...initial, revision: 5 })));
      expect(await submitted).toBe(true);
    });
    expect(payloads.map((p) => [p.command.action, p.revision])).toEqual([
      ['read', 4],
      ['ask', 5],
    ]);
  } finally {
    await act(() => root.unmount());
    vi.unstubAllGlobals();
  }
});
