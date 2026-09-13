export default function(component) {
    const {data, parentElement, setTriggerValue} = component;
    const article = document.createElement('article');
    article.className = 'narrative';
    article.style.fontSize = `${Number(data.font_size) || 17}px`;
    // HTML is rendered by MarkdownIt with raw HTML disabled on the Python side.
    article.innerHTML = data.html;
    parentElement.appendChild(article);
    const click = (event) => {
        const button = event.target.closest('button[data-character-id]');
        if (!button || !article.contains(button)) return;
        event.preventDefault();
        setTriggerValue('character', button.dataset.characterId);
    };
    article.addEventListener('click', click);
    return () => {
        article.removeEventListener('click', click);
        article.remove();
    };
}
