'use client';

import React, { useEffect, useRef, useState } from 'react';
import {
  ArrowLeft,
  Ban,
  BookOpenCheck,
  ChevronLeft,
  ChevronRight,
  Clock3,
  HelpCircle,
  ListChecks,
  MessageSquareText,
  RotateCw,
  ShieldCheck,
} from 'lucide-react';

import { ApiError } from '../../services/apiClient';
import {
  clientScenarioLabels,
  clientScenarioService,
  type ClientScenarioDetail,
  type ClientScenarioPage,
  type ClientScenarioSummary,
} from '../../services/clientScenarioService';


const PAGE_SIZE = 9;

function scrollToTop(): void {
  const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  window.scrollTo({ top: 0, behavior: reducedMotion ? 'auto' : 'smooth' });
}

function requestErrorMessage(error: unknown, detail = false): string {
  if (error instanceof ApiError && error.problem.status === 404) {
    return 'Este escenario ya no está disponible para tu empresa.';
  }
  return detail
    ? 'No pudimos cargar la información del escenario. Inténtalo nuevamente.'
    : 'No pudimos cargar los escenarios disponibles. Inténtalo nuevamente.';
}

function ScenarioCard({
  scenario,
  onOpen,
}: {
  scenario: ClientScenarioSummary;
  onOpen: (scenarioId: string) => void;
}) {
  const titleId = `scenario-${scenario.id}-title`;

  return (
    <article className="client-scenario-card" aria-labelledby={titleId}>
      <button
        type="button"
        className="client-scenario-card-button"
        data-client-scenario-id={scenario.id}
        onClick={() => onOpen(scenario.id)}
      >
        <span className="client-scenario-card-topline">
          <span className="client-scenario-badge">
            {clientScenarioLabels.category[scenario.category]}
          </span>
          <span className="client-scenario-difficulty">
            {clientScenarioLabels.difficulty[scenario.difficulty]}
          </span>
        </span>

        <span id={titleId} className="client-scenario-card-title">
          {scenario.title}
        </span>

        <span className="client-scenario-card-tags">
          <span>{clientScenarioLabels.audience[scenario.audience]}</span>
          <span aria-hidden="true">·</span>
          <span>{clientScenarioLabels.optics[scenario.optics]}</span>
        </span>

        <span className="client-scenario-card-footer">
          <span className="client-scenario-card-facts">
            <span>
              <Clock3 size={15} aria-hidden="true" />
              {scenario.estimatedMinutes} min
            </span>
            <span>
              <HelpCircle size={15} aria-hidden="true" />
              {scenario.questionCount} {scenario.questionCount === 1 ? 'pregunta' : 'preguntas'}
            </span>
          </span>
          <span className="client-scenario-card-link">
            Ver detalle
            <ChevronRight size={16} aria-hidden="true" />
          </span>
        </span>
      </button>
    </article>
  );
}

function ScenarioDetail({
  detail,
  onBack,
}: {
  detail: ClientScenarioDetail;
  onBack: () => void;
}) {
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  return (
    <div className="client-scenarios-view client-scenario-detail">
      <button type="button" className="client-scenario-back" onClick={onBack}>
        <ArrowLeft size={17} aria-hidden="true" />
        Volver a escenarios disponibles
      </button>

      <article aria-labelledby="client-scenario-detail-title">
        <header className="client-scenario-detail-hero">
          <div className="client-scenario-detail-heading">
            <div className="client-scenario-detail-kicker">
              <span className="client-scenario-badge">
                {clientScenarioLabels.category[detail.category]}
              </span>
              <span className="client-scenario-difficulty">
                {clientScenarioLabels.difficulty[detail.difficulty]}
              </span>
            </div>
            <h1
              id="client-scenario-detail-title"
              ref={headingRef}
              tabIndex={-1}
            >
              {detail.title}
            </h1>
            <p>
              Consulta la información preparada para este escenario. Esta vista no permite
              realizar modificaciones.
            </p>
          </div>
          <span className="client-scenario-readonly">
            <ShieldCheck size={17} aria-hidden="true" />
            Solo lectura
          </span>

          <dl className="client-scenario-detail-meta">
            <div>
              <dt>Duración estimada</dt>
              <dd><Clock3 size={16} aria-hidden="true" /> {detail.estimatedMinutes} minutos</dd>
            </div>
            <div>
              <dt>Preguntas</dt>
              <dd><HelpCircle size={16} aria-hidden="true" /> {detail.questionCount}</dd>
            </div>
            <div>
              <dt>Público interno</dt>
              <dd>{clientScenarioLabels.audience[detail.audience]}</dd>
            </div>
            <div>
              <dt>Óptica</dt>
              <dd>{clientScenarioLabels.optics[detail.optics]}</dd>
            </div>
          </dl>
        </header>

        <section className="client-scenario-section" aria-labelledby="scenario-context-title">
          <div className="client-scenario-section-title">
            <BookOpenCheck size={19} aria-hidden="true" />
            <h2 id="scenario-context-title">Contexto</h2>
          </div>
          <p className="client-scenario-context">{detail.context}</p>
        </section>

        <div className="client-scenario-message-grid">
          <section className="client-scenario-section" aria-labelledby="scenario-messages-title">
            <div className="client-scenario-section-title">
              <MessageSquareText size={19} aria-hidden="true" />
              <h2 id="scenario-messages-title">Mensajes clave</h2>
            </div>
            {detail.keyMessages.length ? (
              <ul className="client-scenario-points">
                {detail.keyMessages.map((message, index) => (
                  <li key={`${index}-${message}`}>{message}</li>
                ))}
              </ul>
            ) : (
              <p className="client-scenario-empty-copy">No hay mensajes clave configurados.</p>
            )}
          </section>

          <section
            className="client-scenario-section client-scenario-red-lines"
            aria-labelledby="scenario-red-lines-title"
          >
            <div className="client-scenario-section-title">
              <Ban size={19} aria-hidden="true" />
              <h2 id="scenario-red-lines-title">Líneas rojas</h2>
            </div>
            {detail.redLines.length ? (
              <ul className="client-scenario-points">
                {detail.redLines.map((line, index) => (
                  <li key={`${index}-${line}`}>{line}</li>
                ))}
              </ul>
            ) : (
              <p className="client-scenario-empty-copy">No hay líneas rojas configuradas.</p>
            )}
          </section>
        </div>

        <section className="client-scenario-section" aria-labelledby="scenario-questions-title">
          <div className="client-scenario-section-title client-scenario-question-heading">
            <span>
              <ListChecks size={19} aria-hidden="true" />
              <h2 id="scenario-questions-title">Preguntas del escenario</h2>
            </span>
            <span>{detail.questions.length}</span>
          </div>
          {detail.questions.length ? (
            <ol className="client-scenario-questions">
              {detail.questions.map((question) => (
                <li key={question.sequenceNo}>
                  <span aria-hidden="true">{question.sequenceNo}</span>
                  <p>{question.text}</p>
                </li>
              ))}
            </ol>
          ) : (
            <p className="client-scenario-empty-copy">No hay preguntas configuradas.</p>
          )}
        </section>
      </article>
    </div>
  );
}

export function ClientScenariosView() {
  const [page, setPage] = useState(1);
  const [reloadKey, setReloadKey] = useState(0);
  const [catalog, setCatalog] = useState<ClientScenarioPage | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [isCatalogLoading, setCatalogLoading] = useState(true);
  const [selectedScenarioId, setSelectedScenarioId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ClientScenarioDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const detailRequest = useRef(0);

  useEffect(() => {
    let active = true;
    clientScenarioService.list({ page, pageSize: PAGE_SIZE })
      .then((response) => {
        if (active) setCatalog(response);
      })
      .catch((error: unknown) => {
        if (active) setCatalogError(requestErrorMessage(error));
      })
      .finally(() => {
        if (active) setCatalogLoading(false);
      });
    return () => {
      active = false;
    };
  }, [page, reloadKey]);

  useEffect(() => () => {
    detailRequest.current += 1;
  }, []);

  const openScenario = async (scenarioId: string) => {
    const request = detailRequest.current + 1;
    detailRequest.current = request;
    setSelectedScenarioId(scenarioId);
    setDetail(null);
    setDetailError(null);
    scrollToTop();

    try {
      const response = await clientScenarioService.get(scenarioId);
      if (detailRequest.current === request) setDetail(response);
    } catch (error: unknown) {
      if (detailRequest.current === request) setDetailError(requestErrorMessage(error, true));
    }
  };

  const closeDetail = () => {
    const scenarioId = selectedScenarioId;
    detailRequest.current += 1;
    setSelectedScenarioId(null);
    setDetail(null);
    setDetailError(null);
    window.requestAnimationFrame(() => {
      const buttons = document.querySelectorAll<HTMLButtonElement>('[data-client-scenario-id]');
      Array.from(buttons).find(
        (button) => button.dataset.clientScenarioId === scenarioId,
      )?.focus();
    });
  };

  const changePage = (nextPage: number) => {
    setCatalogLoading(true);
    setCatalogError(null);
    setPage(nextPage);
  };

  const retryCatalog = () => {
    setCatalogLoading(true);
    setCatalogError(null);
    setReloadKey((key) => key + 1);
  };

  const retryDetail = () => {
    if (selectedScenarioId) void openScenario(selectedScenarioId);
  };

  if (selectedScenarioId) {
    if (detail) return <ScenarioDetail detail={detail} onBack={closeDetail} />;

    return (
      <div className="client-scenarios-view">
        <button type="button" className="client-scenario-back" onClick={closeDetail}>
          <ArrowLeft size={17} aria-hidden="true" />
          Volver a escenarios disponibles
        </button>
        <div
          className={`client-scenario-state ${detailError ? 'is-error' : ''}`}
          role={detailError ? 'alert' : 'status'}
          aria-live={detailError ? 'assertive' : 'polite'}
        >
          {detailError ? (
            <>
              <Ban size={28} aria-hidden="true" />
              <h1>No se pudo mostrar el escenario</h1>
              <p>{detailError}</p>
              <button type="button" className="btn nav" onClick={retryDetail}>
                <RotateCw size={15} aria-hidden="true" />
                Reintentar
              </button>
            </>
          ) : (
            <>
              <span className="client-scenario-spinner" aria-hidden="true" />
              <h1>Cargando detalle del escenario</h1>
              <p>Estamos recuperando su información.</p>
            </>
          )}
        </div>
      </div>
    );
  }

  const totalPages = Math.max(1, Math.ceil((catalog?.total ?? 0) / PAGE_SIZE));

  return (
    <section className="client-scenarios-view" aria-labelledby="client-scenarios-title">
      <header className="client-scenarios-heading">
        <div>
          <span className="client-scenarios-eyebrow">
            <BookOpenCheck size={16} aria-hidden="true" />
            Catálogo del cliente
          </span>
          <h1 id="client-scenarios-title">Escenarios disponibles</h1>
          <p>Consulta los escenarios activos asignados a tu empresa y revisa su contenido.</p>
        </div>
        <span className="client-scenario-readonly">
          <ShieldCheck size={17} aria-hidden="true" />
          Solo lectura
        </span>
      </header>

      <div className="client-scenarios-summary" aria-live="polite">
        <span>
          <strong>{catalog?.total ?? 0}</strong>
          {catalog?.total === 1 ? ' escenario disponible' : ' escenarios disponibles'}
        </span>
        {catalog && catalog.total > 0 && (
          <span>Página {page} de {totalPages}</span>
        )}
      </div>

      {isCatalogLoading ? (
        <div className="client-scenario-state" role="status" aria-live="polite">
          <span className="client-scenario-spinner" aria-hidden="true" />
          <h2>Cargando escenarios disponibles</h2>
          <p>Estamos consultando el catálogo de tu empresa.</p>
        </div>
      ) : catalogError ? (
        <div className="client-scenario-state is-error" role="alert">
          <Ban size={28} aria-hidden="true" />
          <h2>No se pudo cargar el catálogo</h2>
          <p>{catalogError}</p>
          <button type="button" className="btn nav" onClick={retryCatalog}>
            <RotateCw size={15} aria-hidden="true" />
            Reintentar
          </button>
        </div>
      ) : !catalog?.items.length ? (
        <div className="client-scenario-state" role="status">
          <BookOpenCheck size={30} aria-hidden="true" />
          <h2>No hay escenarios disponibles</h2>
          <p>Cuando se te asigne un escenario activo, aparecerá en este catálogo.</p>
        </div>
      ) : (
        <>
          <div className="client-scenario-grid">
            {catalog.items.map((scenario) => (
              <ScenarioCard key={scenario.id} scenario={scenario} onOpen={openScenario} />
            ))}
          </div>

          {totalPages > 1 && (
            <nav className="client-scenario-pagination" aria-label="Páginas de escenarios">
              <button
                type="button"
                className="btn"
                disabled={page === 1}
                onClick={() => changePage(Math.max(1, page - 1))}
              >
                <ChevronLeft size={16} aria-hidden="true" />
                Anterior
              </button>
              <span aria-current="page">Página {page} de {totalPages}</span>
              <button
                type="button"
                className="btn"
                disabled={page === totalPages}
                onClick={() => changePage(Math.min(totalPages, page + 1))}
              >
                Siguiente
                <ChevronRight size={16} aria-hidden="true" />
              </button>
            </nav>
          )}
        </>
      )}
    </section>
  );
}
