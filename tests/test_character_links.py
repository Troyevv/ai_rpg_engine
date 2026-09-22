from character_links import linked_markdown


def test_safe_links_and_ambiguous_names():
    characters = [
        {'id': 'one', 'name': 'Анна Орлова', 'aliases': ['Аня', 'Анне']},
        {'id': 'two', 'name': 'Анна Иванова'},
        {'id': 'three', 'name': 'Илья Морозов (ГГ)'},
    ]
    html = linked_markdown('**Анна Орлова** и Анна. Аня говорит Илье. Анне ответили.\n'
                           '`Анна Орлова` [Анна Орлова](https://example.org)\n'
                           '<script>alert(1)</script>\n```\nАня\n```', characters)
    assert html.count('data-character-id="one"') == 3
    assert '<strong><button' in html
    assert '<code>Анна Орлова</code>' in html
    assert '<a href="https://example.org">Анна Орлова</a>' in html
    assert '<script>' not in html
    assert 'и Анна.' in html
    assert linked_markdown('Илья', characters).count('data-character-id="three"') == 1
