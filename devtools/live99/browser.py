"""Playwright player actions. Only diagnostics and polling use GET endpoints."""
import json
import re
import time

from .scenarios import CASES


def expect(locator):
    # Storage/budget recovery tests do not require the optional browser package.
    from playwright.sync_api import expect as browser_expect
    return browser_expect(locator)


def button(page, name):
    return page.get_by_role('button', name=name, exact=True)


def open_save(context, base, seed):
    page = context.new_page()
    page.set_default_timeout(12000)
    selection = json.dumps({k: seed[k] for k in ('save', 'world')})
    page.add_init_script(f"localStorage.setItem('selection',JSON.stringify({selection}));"
                         "localStorage.setItem('profile','live99');")
    page.goto(base)
    expect(page.locator('.current-game-entry button')).to_be_visible()
    expect(page.get_by_label('Своё действие или реплика')).to_be_visible()
    return page


def nav(page, name):
    if page.viewport_size['width'] < 768:
        button(page, 'Меню игры').click()
    button(page, name).last.click()


def inspect_ui(page, case):
    minimize_call(page)
    if case == 'phone':
        page.get_by_role('button', name=re.compile('^Телефон')).click()
        phone = page.get_by_role('region', name='Телефон персонажа')
        button(phone, 'Переписки').click()
        expect(phone.get_by_text('Общая переписка').first).to_be_visible()
    elif case in ('campaign', 'family'):
        nav(page, 'Календарь' if case == 'campaign' else 'Родословная')
        expect(page.locator('.save-workspace:visible')).to_be_visible()
        # The lazy workspace shell appears before its API data. Inspect real
        # fixture content, not a transient "Loading" screen.
        expect(page.locator('.calendar-day-number' if case == 'campaign' else '.family-node').first).to_be_visible()
    else:
        nav(page, {'knowledge': 'Персонажи', 'social': 'Отношения', 'crisis': 'Мир'}[case])
        expect(page.locator('.inspector-workspace')).to_be_visible()
        if case == 'knowledge':
            expect(page.locator('.character-profile')).to_be_visible()
    if page.evaluate('document.documentElement.scrollWidth > innerWidth'):
        raise ValueError('Horizontal overflow')


def game_action(page, tab, name):
    page.locator('.current-game-entry button').click()
    menu = page.get_by_role('dialog').last
    menu.get_by_role('tab', name=tab, exact=True).click()
    button(menu, name).click()
    return page.get_by_role('dialog').last


def plan(case, index, before):
    if not before['last_turn']:
        return 'start', ''
    if case == 'campaign' and 1 <= index <= 4:
        return ('regenerate', 'variant', 'rollback', 'lta')[index - 1], ''
    if case == 'crisis' and index == 1:
        return 'switch', 'qa_vera'
    if case == 'phone' and index % 5 == 1:
        return 'phone', 'Вера, когда тебе удобно созвониться?'
    actions = CASES[case][1]
    return 'turn', actions[index % len(actions)]


def minimize_call(page):
    call = page.get_by_role('dialog', name='Сцена звонка')
    if call.is_visible():
        button(call, 'Свернуть звонок').click()


def configure_context(page, context_length):
    minimize_call(page)
    if page.viewport_size['width'] < 768:
        button(page, 'Меню игры').click()
    page.get_by_role('button', name='Настройки', exact=True).filter(visible=True).last.click()
    dialog = page.get_by_role('dialog').last
    dialog.get_by_label('Контекст game', exact=True).fill(str(context_length))
    button(dialog, 'Сохранить настройки').click()
    expect(dialog).not_to_be_visible()


def wait_phone_read(page, base, sid, action):
    """Opening a chat performs a canonical read; await it before the reload baseline."""
    for _ in range(40):
        projection = page.request.get(f'{base}/api/saves/{sid}').json()
        events = projection['state']['phone']['events']
        outgoing = [e for e in events if e['outgoing'] and e.get('content') == action]
        if outgoing:
            conversation = outgoing[-1]['conversation_id']
            if not any(e['conversation_id'] == conversation and e['unread'] for e in events):
                return
        page.wait_for_timeout(250)
    raise ValueError('Selected conversation still has an unapplied read; preserve the paid job')


def play(page, base, sid, kind, action, choice_index=None, job_id=None, options=None):
    prefix = f'{base}/api/saves/{sid}'
    endpoint = {'phone':'/phone/dispatch', 'phone-group':'/phone/dispatch', 'phone-call':'/phone/dispatch',
                'call-end':'/phone', 'switch':'/protagonist', 'lta':'/long-term',
                'rollback':'/rollback', 'variant':'/variant'}.get(kind, '/turns')

    def matches(response):
        if kind == 'abandon':
            return response.url == f'{prefix}/jobs/{job_id}/abandon' and response.request.method == 'POST'
        if kind in ('retry', 'phone-retry'):
            return response.url == f'{base}/api/jobs/{job_id}/retry' and response.request.method == 'POST'
        return (response.url.startswith(prefix + '/') and response.url.endswith(endpoint)
                and response.request.method == 'POST'
                and (kind != 'switch' or not response.request.post_data_json.get('preview')))

    with page.expect_response(matches) as pending:
        if kind == 'abandon':
            page.get_by_label('Своё действие или реплика').fill(action)
            button(page, 'Отменить неудачный ход').click()
        elif kind == 'retry':
            button(page, 'Повторить обработку состояния').click()
        elif kind == 'phone-retry':
            phone = page.get_by_role('region', name='Телефон персонажа')
            if not phone.is_visible():
                page.get_by_role('button', name=re.compile('^Телефон')).click()
            button(phone, 'Переписки').click()
            phone.get_by_role('button', name=re.compile('Вера')).first.click()
            button(phone, 'Повторить').click()
        elif kind == 'start':
            button(page, 'Начать игру').click()
        elif kind == 'background':
            button(page, 'Мир без ГГ').click()
        elif kind == 'call-speech':
            call = page.get_by_role('dialog', name='Сцена звонка')
            if not call.is_visible():
                page.get_by_role('button', name=re.compile('Вернуться к звонку')).click()
            call.get_by_label('Реплика в звонке').fill(action)
            call.get_by_label('Сказать собеседнику').click()
        elif kind == 'call-end':
            call = page.get_by_role('dialog', name='Сцена звонка')
            if not call.is_visible():
                page.get_by_role('button', name=re.compile('Вернуться к звонку')).click()
            button(call, 'Завершить звонок').click()
        elif kind == 'turn':
            page.get_by_label('Своё действие или реплика').fill(action)
            button(page, 'Отправить действие').click()
        elif kind == 'choice':
            choice = page.locator('.choices button').nth(choice_index)
            if choice.inner_text() != action:
                raise ValueError('Choices changed before dispatch')
            choice.click()
        elif kind == 'regenerate':
            button(page, 'Перегенерировать последний ход').click()
        elif kind == 'rollback':
            page.once('dialog', lambda dialog: dialog.accept())
            button(page, 'Откатить').click()
        elif kind == 'variant':
            turn = page.locator('.turn').last
            prev = button(turn, 'Предыдущий вариант')
            (prev if prev.is_visible() else button(turn.locator('.variant-controls'), '1')).click()
        elif kind == 'lta':
            dialog = game_action(page, 'Время', 'Длительный переход')
            dialog.get_by_label('Количество единиц перехода').fill(str((options or {}).get('amount', 2)))
            if (options or {}).get('unit'):
                dialog.get_by_label('Единица перехода').select_option(options['unit'])
            dialog.get_by_text(re.compile('Подробности симуляции')).click()
            dialog.get_by_label('Лимит обращений к модели').fill(str((options or {}).get('model_budget', 1)))
            button(dialog, 'Подтвердить длительный переход').click()
        elif kind == 'switch':
            dialog = game_action(page, 'Персонажи', 'Сменить главного героя')
            dialog.get_by_label('Новый главный герой').select_option(action)
            button(dialog, 'Проверить и посмотреть').click()
            button(dialog, 'Подтвердить смену').click()
        elif kind in ('phone', 'phone-call', 'phone-group'):
            page.get_by_role('button', name=re.compile('^Телефон')).click()
            phone = page.get_by_role('region', name='Телефон персонажа')
            if kind == 'phone-group':
                button(phone, 'Переписки').click()
                phone.locator('.phone-thread').filter(has_text='Общая переписка').click()
            else:
                button(phone, 'Контакты').click()
                phone.get_by_label('Поиск адресата').fill('Вера')
                phone.get_by_role('button', name=re.compile(
                    'Позвонить: Вера' if kind == 'phone-call' else 'Написать: Вера')).first.click()
            if kind != 'phone-call':
                phone.get_by_label('Сообщение в телефоне').fill(action)
                button(phone, 'Отправить сообщение').click()
    response = pending.value
    if not response.ok:
        raise ValueError(f'{endpoint} HTTP {response.status}: {response.text()[:500]}')
    result = response.json()
    if kind == 'abandon':
        if result.get('status') != 'abandoned':
            raise ValueError('Abandon did not terminate the selected rejected job')
        expect(page.get_by_label('Своё действие или реплика')).to_have_value(action)
        expect(button(page, 'Отправить действие')).to_be_enabled()
    job = result.get('job') if kind in ('phone','phone-call','phone-group') else result
    if kind in ('start','turn','choice','phone','phone-call','phone-group','call-speech','background','regenerate','lta','retry','phone-retry'):
        deadline = time.monotonic() + 240
        while job['status'] in ('generating','extracting','validating') and time.monotonic() < deadline:
            page.wait_for_timeout(600)
            job = page.request.get(base + '/api/jobs/' + job['id']).json()
        if job['status'] in ('generating','extracting','validating'):
            page.request.post(base + '/api/jobs/' + job['id'] + '/stop', data={})
        if job['status'] != 'saved':
            raise ValueError(f"Job {job['id']} status {job['status']}: {job.get('error', '')}")
    if kind in ('phone','phone-group'):
        expect(page.locator('.phone-message.outgoing').filter(has_text=action).last).to_be_visible()
        wait_phone_read(page, base, sid, action)


def compare_prose(page, base, sid, world, text):
    # Compare the entire rendered passage with the ordinary Markdown projection
    # of the persisted text. No fuzzy literary judgment or keyword matching.
    result = page.request.post(base + '/api/markdown', data=dict(text=text, save_id=sid, world_id=world))
    if not result.ok:
        raise ValueError('Markdown diagnostic unavailable')
    expected = page.evaluate("""html => new DOMParser().parseFromString(html,'text/html').body.textContent""",
                             result.json()['html'])
    expect(page.locator('.turn .narrative-text').last).to_have_text(expected, timeout=45000)
