// Figures of an article the research already read. The caption and the anchor in the source are
// the evidence and come from the stored record; the image is a convenience that is shown only when
// it has actually been retrieved. A figure that was not retrieved says so and still links out.

function articleFigureCaption(text) {
  // Publishers prepend "Figure 3" and append a boilerplate accessibility line; both are noise here.
  const clean = String(text || '').replace(/For image description[^]*$/i, '').trim();
  const match = /^((?:Figure|Fig\.?|Table)\s*\d+[.:]?)\s*([^]*)$/i.exec(clean);
  return match ? {label: match[1].trim(), body: match[2].trim()} : {label: '', body: clean};
}

function articleFigureImage(figure, workspaceId, artifactId) {
  const full = (figure.available || []).find(a => a.cached && !/\.gif$/i.test(a.file))
    || (figure.available || []).find(a => a.cached);
  if (!full) {
    return `<p class="small muted">그림 파일은 아직 회수되지 않았습니다. 아래 원문 위치에서 확인할 수 있습니다.</p>`;
  }
  const source = `/api/workspaces/${encodeURIComponent(workspaceId)}/artifacts/${
    encodeURIComponent(artifactId)}?figure=${encodeURIComponent(full.file)}`;
  const {label, body} = articleFigureCaption(figure.caption);
  return `<img class="article-figure-image" loading="lazy" src="${esc(deploymentURL(source))}"
    alt="${esc([label, body].filter(Boolean).join(' ').slice(0, 300))}">`;
}

function articleFiguresView(result, workspaceId, artifactId) {
  const figures = (result && result.figures) || [];
  if (!figures.length) return '';
  const cached = figures.filter(f => (f.available || []).some(a => a.cached)).length;
  const retrieval = result.figure_retrieval || {};
  const retrievalStatus = {failed:'그림 파일 회수를 완료하지 못했습니다.',
    cache_error:'그림 파일 저장 상태를 확인해야 합니다.', started:'이전 그림 회수 작업이 완료되기 전에 중단됐습니다.',
    partial:'일부 그림 파일을 회수했습니다.', not_returned:'이번 공개 응답에는 요청한 그림 파일이 없었습니다.'}[retrieval.status];
  return `<details class="article-figures" open>
    <summary>원문 그림 ${esc(figures.length)}개${cached < figures.length
      ? ` · 회수된 이미지 ${esc(cached)}개` : ''}</summary>
    ${retrievalStatus ? `<p class="small muted">${esc(retrievalStatus)} 저장된 캡션과 원문 위치는 계속 확인할 수 있습니다.</p>` : ''}
    <div class="article-figure-grid">${figures.map(figure => {
      const {label, body} = articleFigureCaption(figure.caption);
      return `<figure class="article-figure">
        ${articleFigureImage(figure, workspaceId, artifactId)}
        <figcaption>
          ${label ? `<strong>${esc(label)}</strong> ` : ''}${esc(body)}
          <span class="small muted">${esc(figure.section || '')}</span>
          ${figure.source_url ? `<a href="${esc(figure.source_url)}" target="_blank"
            rel="noopener noreferrer" class="source-link">원문 위치</a>` : ''}
        </figcaption>
      </figure>`;
    }).join('')}</div>
    <p class="limit">저자가 논문에 실은 그림입니다. 캡션과 원문 위치가 근거이고, 그림 자체는 읽기를
      돕기 위한 것입니다. 이 화면이 그림을 해석하거나 새로 계산하지 않습니다.</p>
  </details>`;
}
