import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { helpLinks, lessons, meetings, steps } from './content';
import './style.css';

const pages = {
  program: 'О программе',
  materials: 'Материалы',
  contacts: 'Контакты',
  route: 'Маршрут к работе',
};

function readPage() {
  const id = location.hash.slice(1);
  return Object.hasOwn(pages, id) ? id : 'program';
}

async function api(path, options) {
  const response = await fetch('/api/' + path, options);
  if (!response.ok) throw new Error('Запрос не выполнен');
  return response.json();
}

function LinkButton({ to, children, secondary = false }) {
  return <a className={secondary ? 'button secondary' : 'button'} href={'#' + to}>{children}<span aria-hidden="true">↗</span></a>;
}

function App() {
  const [page, setPage] = useState(readPage);
  const [catalog, setCatalog] = useState(null);
  const [catalogError, setCatalogError] = useState(false);
  const main = useRef(null);
  const previousPage = useRef(page);

  function loadCatalog() {
    setCatalogError(false);
    api('program').then(setCatalog).catch(() => setCatalogError(true));
  }

  useEffect(() => {
    loadCatalog();
    const onHash = () => setPage(readPage());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  useEffect(() => {
    document.title = pages[page] + ' — Первые 100 дней';
    if (previousPage.current !== page) {
      window.scrollTo(0, 0);
      main.current?.focus({ preventScroll: true });
      previousPage.current = page;
    }
  }, [page]);

  return <>
    <a className="skip" href="#main" onClick={event => { event.preventDefault(); main.current?.focus(); }}>К содержанию</a>
    <header className="header">
      <div className="shell header-inner">
        <a className="brand" href="#program" aria-label="Первые 100 дней, главная">
          <span className="brand-mark" aria-hidden="true">100<span>↗</span></span><span>Первые<br />100 дней</span>
        </a>
        <nav aria-label="Главное меню">
          {['program', 'materials', 'contacts'].map(id => <a key={id} href={'#' + id} aria-current={page === id ? 'page' : undefined}>{pages[id]}</a>)}
        </nav>
        <a className="header-route" href="#route" aria-current={page === 'route' ? 'page' : undefined}>Маршрут к работе <span aria-hidden="true">↗</span></a>
      </div>
    </header>
    <main id="main" tabIndex={-1} ref={main}>
      {page === 'program' && <Program />}
      {page === 'materials' && <Materials items={catalog?.materials} error={catalogError} retry={loadCatalog} />}
      {page === 'contacts' && <Contacts catalog={catalog} error={catalogError} retry={loadCatalog} />}
      {page === 'route' && <Route />}
    </main>
    <footer className="footer">
      <div className="shell footer-inner">
        <a href="#program" className="footer-name">Первые 100 дней</a>
        <p>Программа подготовки к самостоятельной жизни</p>
        <a href="#contacts">Куда обратиться <span aria-hidden="true">↗</span></a>
      </div>
    </footer>
  </>;
}

function Program() {
  return <>
    <section className="shell hero">
      <div className="hero-copy">
        <p className="kicker">Программа для выпускников детских домов</p>
        <h1>Первые<br /><em>100 дней</em></h1>
        <p className="lede">За месяц до выпуска — четыре очных занятия. После выпуска — 100 дней, чтобы сделать первые шаги к своей цели вместе со специалистом.</p>
        <div className="actions"><LinkButton to="route">Попробовать маршрут</LinkButton><a className="text-link" href="#materials">Открыть материалы</a></div>
      </div>
      <figure className="hero-photo">
        <img src="/ochnoe-zanyatie.webp" alt="Участник и специалист разбирают задание за столом" fetchPriority="high" />
        <figcaption><span>Участие бесплатное</span><span>Иллюстрация занятия</span></figcaption>
      </figure>
    </section>
    <section className="shell section lessons">
      <div className="section-intro">
        <p className="kicker">За месяц до выпуска</p>
        <h2>Четыре очных занятия</h2>
        <p>В конце — практическое задание и сертификат участия.</p>
      </div>
      <ol className="lesson-grid">
        {lessons.map(([title, text], index) => <li key={title}><span className="lesson-num">{index + 1}</span><h3>{title}</h3><p>{text}</p></li>)}
      </ol>
    </section>
    <section className="followup">
      <div className="shell section">
        <div className="section-intro">
          <p className="kicker">После выпуска</p>
          <h2>100 дней со специалистом</h2>
          <p>Ты выбираешь свою цель. На встречах вы обсуждаете, что уже получилось и с чем нужна помощь.</p>
        </div>
        <ol className="meeting-grid">
          {meetings.map(([day, title, text]) => <li key={day}><span className="day">День {day}</span><h3>{title}</h3><p>{text}</p></li>)}
        </ol>
        <LinkButton to="route" secondary>Посмотреть маршрут к работе</LinkButton>
      </div>
    </section>
    <section className="shell section pilot">
      <div><p className="kicker">Первый запуск</p><h2>Пилот в Ульяновской области</h2></div>
      <div><p>Планируем провести занятия для одной группы до десяти человек. Команда готовит материалы и организует занятия, а сотрудник учреждения ведёт сопровождение. Площадку и ответственных предстоит согласовать.</p>
      <p>Для пилота предусмотрена предварительная смета 32 600 ₽. На 30-й день проверим первый шаг, а к концу программы подведём итоги по откликам, собеседованиям, предложениям и трудоустройствам участников, выбравших поиск работы.</p></div>
    </section>
  </>;
}

function PageIntro({ title, children }) {
  return <div className="page-intro"><h1>{title}</h1><p className="lede">{children}</p></div>;
}

function LoadError({ retry, children }) {
  return <div className="notice" role="alert"><p>{children}</p><button type="button" className="button secondary" onClick={retry}>Повторить</button></div>;
}

function Materials({ items, error, retry }) {
  return <section className="shell page">
    <PageIntro title="Материалы">Шаблоны и упражнения для занятий. Их можно открыть дома или распечатать.</PageIntro>
    {error && <LoadError retry={retry}>Материалы не загрузились.</LoadError>}
    {!items && !error && <p role="status">Загружаем материалы…</p>}
    <div className="material-list">
      {items?.map(item => <article key={item.id} className="material">
        <span className="material-format">{item.format.toUpperCase()}</span>
        <div><p className="kicker">{item.category}</p><h2>{item.title}</h2><p>{item.description}</p></div>
        <a className="button secondary" download href={'/api/materials/' + item.id + '/download'} aria-label={'Скачать «' + item.title + '»'}>Скачать <span aria-hidden="true">↓</span></a>
      </article>)}
    </div>
  </section>;
}

function Contacts({ catalog, error, retry }) {
  return <section className="shell page">
    <PageIntro title="Контакты">К кому обратиться по вопросам программы, сопровождения и поиска работы.</PageIntro>
    <div className="contact-grid">
      <article className="contact-card">
        <h2>Команда проекта</h2>
        <p>Кирилл Проконов и Степан Филиппов готовят занятия и материалы для первого запуска.</p>
        {catalog?.contactEmail && <a className="text-link" href={'mailto:' + catalog.contactEmail}>Написать команде ↗</a>}
        {catalog && !catalog.contactEmail && <p className="quiet">Контакт команды появится после согласования пилота.</p>}
        {!catalog && !error && <p role="status">Проверяем контакт…</p>}
        {error && <LoadError retry={retry}>Контакт команды не загрузился.</LoadError>}
      </article>
      <article className="contact-card">
        <h2>Социальная поддержка</h2>
        <p>Если ты в Ульяновской области и не знаешь, куда обратиться, позвони на единый социальный телефон.</p>
        <p><a className="text-link" href="tel:+78003504646">8 800 350-46-46</a></p>
        <a href="https://mfc.ulgov.ru/knd/minsoc.php">Минсоцразвития Ульяновской области ↗</a>
      </article>
      {helpLinks.map(link => <article key={link.title} className="contact-card">
        <h2>{link.title}</h2><p>{link.text}</p><a className="text-link" href={link.href}>{link.label} ↗</a>
      </article>)}
    </div>
  </section>;
}

function Route() {
  const [completed, setCompleted] = useState([]);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [meeting, setMeeting] = useState(0);
  const [draft, setDraft] = useState('');

  function loadProgress() {
    setError('');
    setBusy(true);
    api('progress').then(data => { setCompleted(data.completed); setReady(true); })
      .catch(() => setError('Не удалось загрузить отметки.'))
      .finally(() => setBusy(false));
  }

  useEffect(loadProgress, []);

  async function saveProgress(next) {
    setBusy(true);
    setError('');
    try {
      const data = await api('progress', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ completed: next }) });
      setCompleted(data.completed);
    } catch {
      setError('Отметка не сохранилась. Попробуй ещё раз.');
    } finally {
      setBusy(false);
    }
  }

  const next = steps.find(step => !completed.includes(step.id));
  return <section className="shell page route-page">
    <PageIntro title="Маршрут к первой работе">Учебный пример. Попробуй подготовиться к отклику и посмотри, как проходят встречи со специалистом.</PageIntro>
    <div className="route-grid">
      <section className="route-main" aria-labelledby="plan-title">
        <div className="route-heading"><h2 id="plan-title">Мой план</h2><span role="status">{ready ? completed.length + ' из ' + steps.length + ' шагов' : 'Загрузка плана'}</span></div>
        <progress max={steps.length} value={completed.length} aria-label="Выполненные шаги" />
        {error && !ready && <LoadError retry={loadProgress}>{error}</LoadError>}
        {error && ready && <p className="notice" role="alert">{error}</p>}
        {ready && <p className="next-step">{next ? 'Ближайший шаг — ' + next.title.toLowerCase() : 'Все шаги отмечены. На встрече обсуди со специалистом, что делать дальше.'}</p>}
        <ul className="steps">
          {steps.map(step => <li key={step.id}><label>
            <input type="checkbox" checked={completed.includes(step.id)} disabled={!ready || busy}
              onChange={event => saveProgress(event.target.checked ? [...completed, step.id] : completed.filter(id => id !== step.id))} />
            <span><strong>{step.title}</strong><span>{step.detail}</span></span>
          </label></li>)}
        </ul>
        <a className="text-link" href="/api/materials/resume/download" download>Скачать шаблон резюме и отклика ↓</a>
      </section>
      <aside className="route-aside">
        <article className="sample">
          <p className="kicker">Учебная вакансия</p><h2>Помощник в книжном магазине</h2>
          <p>Разбирать поставки, раскладывать книги и помогать покупателям. Опыт не требуется.</p>
          <details><summary>Показать пример отклика</summary><p>Здравствуйте! Хочу откликнуться на вакансию помощника. На практике я работал с таблицами и помогал распределять материалы. Готов учиться и могу выйти на пробную смену после учёбы.</p></details>
          <label className="draft-label" htmlFor="draft">Попробуй написать отклик</label>
          <textarea id="draft" maxLength={600} rows={4} value={draft}
            onChange={event => setDraft(event.target.value)} aria-describedby="draft-tip" />
          <p className="quiet" id="draft-tip">Учебный черновик. Оставь имя и контакты за скобками. Текст исчезнет, когда закроешь маршрут.</p>
        </article>
        <section className="route-meeting" aria-labelledby="meeting-title">
          <h2 id="meeting-title">Встречи со специалистом</h2>
          <label htmlFor="meeting-day">День программы</label>
          <select id="meeting-day" value={meeting} onChange={event => setMeeting(Number(event.target.value))}>
            {meetings.map(([day, title], index) => <option key={day} value={index}>День {day} · {title}</option>)}
          </select>
          <p aria-live="polite">{meetings[meeting][2]}</p>
          <a className="text-link" href="#contacts">Куда обратиться ↗</a>
        </section>
      </aside>
    </div>
  </section>;
}

createRoot(document.getElementById('root')).render(<App />);