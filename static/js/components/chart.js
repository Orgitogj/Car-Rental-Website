

const NS = 'http://www.w3.org/2000/svg';

function el(name, attrs = {}) {
  const node = document.createElementNS(NS, name);
  Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
  return node;
}

/** Catmull-Rom style smoothing, expressed as cubic beziers. */
function smoothPath(points, tension = 0.34) {
  if (points.length < 2) return '';
  let d = `M ${points[0].x} ${points[0].y}`;

  for (let i = 0; i < points.length - 1; i += 1) {
    const p0 = points[i - 1] || points[i];
    const p1 = points[i];
    const p2 = points[i + 1];
    const p3 = points[i + 2] || p2;

    const c1x = p1.x + ((p2.x - p0.x) / 6) * tension * 2;
    const c1y = p1.y + ((p2.y - p0.y) / 6) * tension * 2;
    const c2x = p2.x - ((p3.x - p1.x) / 6) * tension * 2;
    const c2y = p2.y - ((p3.y - p1.y) / 6) * tension * 2;

    d += ` C ${c1x} ${c1y}, ${c2x} ${c2y}, ${p2.x} ${p2.y}`;
  }
  return d;
}

function niceCeil(value) {
  if (value <= 0) return 10;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const scaled = value / magnitude;
  const step = scaled <= 1 ? 1 : scaled <= 2 ? 2 : scaled <= 5 ? 5 : 10;
  return step * magnitude;
}

function drawArea(host, series, options) {
  const { showAxis = true, currency = '' } = options;

  const width = host.clientWidth || 640;
  const height = host.clientHeight || 240;
  const pad = showAxis
    ? { top: 12, right: 8, bottom: 26, left: 46 }
    : { top: 3, right: 2, bottom: 3, left: 2 };

  const innerW = Math.max(width - pad.left - pad.right, 10);
  const innerH = Math.max(height - pad.top - pad.bottom, 10);

  const max = niceCeil(Math.max(...series.map((d) => d.value), 0));
  const stepX = series.length > 1 ? innerW / (series.length - 1) : 0;

  const points = series.map((d, i) => ({
    x: pad.left + i * stepX,
    y: pad.top + innerH - (max ? (d.value / max) * innerH : 0),
    data: d,
  }));

  const svg = el('svg', {
    viewBox: `0 0 ${width} ${height}`,
    preserveAspectRatio: 'none',
    role: 'img',
    'aria-label': options.label || 'Trend chart',
  });

  const gradientId = `grad-${Math.random().toString(36).slice(2, 9)}`;
  const defs = el('defs');
  const gradient = el('linearGradient', {
    id: gradientId,
    x1: '0', y1: '0', x2: '0', y2: '1',
  });
  gradient.append(
    el('stop', { offset: '0%', 'stop-color': 'var(--primary)', 'stop-opacity': '0.28' }),
    el('stop', { offset: '100%', 'stop-color': 'var(--primary)', 'stop-opacity': '0' })
  );
  defs.append(gradient);
  svg.append(defs);

  // Horizontal grid + y labels
  if (showAxis) {
    for (let i = 0; i <= 4; i += 1) {
      const y = pad.top + (innerH / 4) * i;
      svg.append(
        el('line', {
          x1: pad.left, y1: y, x2: width - pad.right, y2: y,
          stroke: 'var(--border-subtle)', 'stroke-width': '1',
        })
      );

      const label = el('text', {
        x: pad.left - 8, y: y + 4,
        'text-anchor': 'end',
        fill: 'var(--text-subtle)',
        'font-size': '10',
      });
      label.textContent = `${currency}${Math.round(max - (max / 4) * i).toLocaleString()}`;
      svg.append(label);
    }
  }

  const line = smoothPath(points);

  if (line) {
    const baseline = pad.top + innerH;
    svg.append(
      el('path', {
        d: `${line} L ${points[points.length - 1].x} ${baseline} L ${points[0].x} ${baseline} Z`,
        fill: `url(#${gradientId})`,
      })
    );

    const stroke = el('path', {
      d: line,
      fill: 'none',
      stroke: 'var(--primary)',
      'stroke-width': showAxis ? '2.2' : '1.8',
      'stroke-linecap': 'round',
      'stroke-linejoin': 'round',
    });
    svg.append(stroke);

    // Draw-on animation, skipped when the user prefers reduced motion.
    if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      const length = stroke.getTotalLength?.() || 0;
      if (length) {
        stroke.style.strokeDasharray = String(length);
        stroke.style.strokeDashoffset = String(length);
        stroke.animate(
          [{ strokeDashoffset: length }, { strokeDashoffset: 0 }],
          { duration: 900, easing: 'cubic-bezier(0.22, 1, 0.36, 1)', fill: 'forwards' }
        );
      }
    }
  }

  // X labels: a handful, evenly spaced
  if (showAxis && series.length) {
    const every = Math.max(1, Math.ceil(series.length / 6));
    series.forEach((d, i) => {
      if (i % every !== 0 && i !== series.length - 1) return;
      const label = el('text', {
        x: pad.left + i * stepX,
        y: height - 8,
        'text-anchor': i === 0 ? 'start' : i === series.length - 1 ? 'end' : 'middle',
        fill: 'var(--text-subtle)',
        'font-size': '10',
      });
      label.textContent = d.label;
      svg.append(label);
    });
  }

  // Hover marker + tooltip
  if (showAxis && points.length) {
    const marker = el('circle', {
      r: '4.5',
      fill: 'var(--surface)',
      stroke: 'var(--primary)',
      'stroke-width': '2.5',
      opacity: '0',
    });
    svg.append(marker);

    let tooltip = host.querySelector('.chart__tooltip');
    if (!tooltip) {
      tooltip = document.createElement('div');
      tooltip.className = 'chart__tooltip';
      host.appendChild(tooltip);
    }

    const overlay = el('rect', {
      x: pad.left, y: pad.top, width: innerW, height: innerH, fill: 'transparent',
    });
    svg.append(overlay);

    overlay.addEventListener('mousemove', (event) => {
      const bounds = svg.getBoundingClientRect();
      const ratio = width / bounds.width;
      const x = (event.clientX - bounds.left) * ratio;
      const index = Math.min(
        series.length - 1,
        Math.max(0, Math.round((x - pad.left) / (stepX || 1)))
      );
      const point = points[index];

      marker.setAttribute('cx', point.x);
      marker.setAttribute('cy', point.y);
      marker.setAttribute('opacity', '1');

      tooltip.textContent = `${point.data.label} · ${currency}${point.data.value.toLocaleString()}`;
      tooltip.style.left = `${(point.x / ratio)}px`;
      tooltip.style.top = `${(point.y / ratio)}px`;
      tooltip.classList.add('is-visible');
    });

    overlay.addEventListener('mouseleave', () => {
      marker.setAttribute('opacity', '0');
      tooltip.classList.remove('is-visible');
    });
  }

  host.querySelector('svg')?.remove();
  host.prepend(svg);
}

export function initCharts(root = document) {
  const hosts = root.querySelectorAll('[data-chart]');
  if (!hosts.length) return;

  hosts.forEach((host) => {
    let series;
    try {
      series = JSON.parse(host.dataset.series || '[]');
    } catch {
      return;
    }
    if (!Array.isArray(series) || !series.length) return;

    const options = {
      showAxis: host.dataset.chart !== 'spark',
      currency: host.dataset.currency || '',
      label: host.dataset.label,
    };

    const render = () => drawArea(host, series, options);
    render();

    // Redraw on resize, throttled by rAF.
    let frame;
    new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(render);
    }).observe(host);
  });
}
