'use client';

import React, { useState, useEffect } from 'react';
import { useI18n } from '../../context/I18nContext';
import { AdminScreen } from './ClientDashboard';
import { topicService } from '../../services/topicService';
import { InstitutionalOptics, InternalAudience } from '../../types/api';

interface TopicEditorViewProps {
  onNavigate: (screen: AdminScreen) => void;
  topicId?: string | null;
}

export const TopicEditorView: React.FC<TopicEditorViewProps> = ({ onNavigate, topicId }) => {
  const { t } = useI18n();
  const d = t.L.a2;

  const isNew = !topicId || topicId === 'new';

  const [topicName, setTopicName] = useState('');
  const [contextText, setContextText] = useState('');
  const [selectedOptic, setSelectedOptic] = useState<InstitutionalOptics>('Empática');
  const [selectedAudience, setSelectedAudience] = useState<InternalAudience>('Dirección');
  const [selectedLanguages, setSelectedLanguages] = useState<string[]>(['ES']);
  const [keyMessages, setKeyMessages] = useState<string[]>([]);
  const [redLines, setRedLines] = useState<string[]>([]);

  const [newKeyInput, setNewKeyInput] = useState('');
  const [newRedInput, setNewRedInput] = useState('');

  const [isLoading, setIsLoading] = useState(!isNew);
  const [isSaving, setIsSaving] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [showSavedNotification, setShowSavedNotification] = useState(false);

  // Cargar datos si estamos editando
  useEffect(() => {
    let isMounted = true;

    async function loadTopic() {
      if (!isNew && topicId) {
        setIsLoading(true);
        const topic = await topicService.getTopicById(topicId);
        if (isMounted && topic) {
          setTopicName(topic.name);
          setContextText(topic.context);
          setSelectedOptic(topic.optics || 'Empática');
          setSelectedAudience(topic.audience || 'Dirección');
          setSelectedLanguages(topic.languages && topic.languages.length > 0 ? topic.languages : ['ES']);
          setKeyMessages(topic.keyMessages || []);
          setRedLines(topic.redLines || []);
        }
        setIsLoading(false);
      } else {
        // Valores por defecto para nuevo tema
        setTopicName('');
        setContextText('');
        setSelectedOptic('Empática');
        setSelectedAudience('Dirección');
        setSelectedLanguages(['ES']);
        setKeyMessages([]);
        setRedLines([]);
        setIsLoading(false);
      }
    }

    loadTopic();

    return () => {
      isMounted = false;
    };
  }, [topicId, isNew]);

  const handleToggleLanguage = (lang: string) => {
    if (selectedLanguages.includes(lang)) {
      if (selectedLanguages.length > 1) {
        setSelectedLanguages(selectedLanguages.filter((l) => l !== lang));
      }
    } else {
      setSelectedLanguages([...selectedLanguages, lang]);
    }
  };

  const handleAddKey = () => {
    if (newKeyInput.trim()) {
      setKeyMessages([...keyMessages, newKeyInput.trim()]);
      setNewKeyInput('');
      setErrorMsg(null);
    }
  };

  const handleRemoveKey = (idx: number) => {
    setKeyMessages(keyMessages.filter((_, i) => i !== idx));
  };

  const handleAddRed = () => {
    if (newRedInput.trim()) {
      setRedLines([...redLines, newRedInput.trim()]);
      setNewRedInput('');
    }
  };

  const handleRemoveRed = (idx: number) => {
    setRedLines(redLines.filter((_, i) => i !== idx));
  };

  const handleSave = async () => {
    if (!topicName.trim()) {
      setErrorMsg('Por favor ingresa el nombre del tema.');
      return;
    }

    if (!contextText.trim()) {
      setErrorMsg('Por favor describe el contexto o situación del tema.');
      return;
    }

    if (keyMessages.length === 0) {
      setErrorMsg('Agrega al menos un mensaje clave institucional.');
      return;
    }

    setErrorMsg(null);
    setIsSaving(true);

    try {
      await topicService.saveTopic({
        id: isNew ? undefined : topicId!,
        name: topicName.trim(),
        context: contextText.trim(),
        optics: selectedOptic,
        audience: selectedAudience,
        languages: selectedLanguages,
        keyMessages,
        redLines
      });

      setShowSavedNotification(true);
      setTimeout(() => {
        onNavigate('a1');
      }, 700);
    } catch (err: any) {
      setErrorMsg(err?.message || 'Error al guardar el tema. Intenta nuevamente.');
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return (
      <div className="canvas-content" style={{ textAlign: 'center', padding: '40px' }}>
        <p style={{ color: 'var(--muted)' }}>Cargando datos del tema...</p>
      </div>
    );
  }

  const opticsOptions: InstitutionalOptics[] = ['Empática', 'Formal', 'Técnica'];
  const audienceOptions: InternalAudience[] = ['Dirección', 'Planta', 'Técnicos'];
  const availableLanguages = ['ES', 'EN', 'PT'];

  return (
    <div className="canvas-content">
      {/* Header Bar */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '20px'
        }}
      >
        <div>
          <h2 style={{ margin: 0, fontSize: '20px', fontWeight: 700, color: 'var(--ink)' }}>
            {isNew ? '➕ Nuevo Tema Institucional' : `✏️ Editar Tema: ${topicName || ''}`}
          </h2>
          <span style={{ fontSize: '13px', color: 'var(--muted)' }}>
            {isNew
              ? 'Configura un nuevo escenario de crisis para los voceros de la organización.'
              : 'Modifica los lineamientos, mensajes clave y líneas rojas del tema.'}
          </span>
        </div>
        <button
          type="button"
          className="btn ghost"
          onClick={() => onNavigate('a1')}
        >
          ← Volver a la lista
        </button>
      </div>

      {showSavedNotification && (
        <div
          style={{
            padding: '12px 18px',
            marginBottom: '16px',
            borderRadius: '8px',
            background: 'var(--accentsoft)',
            color: 'var(--accent)',
            border: '1px solid var(--accent)',
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            gap: '8px'
          }}
        >
          <span>✓</span>
          <span>Tema guardado con éxito. Redirigiendo a la lista...</span>
        </div>
      )}

      {errorMsg && (
        <div
          style={{
            padding: '12px 18px',
            marginBottom: '16px',
            borderRadius: '8px',
            background: '#ffe5e5',
            color: 'var(--danger)',
            border: '1px solid var(--danger)',
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            gap: '8px'
          }}
        >
          <span>⚠️</span>
          <span>{errorMsg}</span>
        </div>
      )}

      <div className="row">
        {/* Left Column */}
        <div className="col">
          <div className="label">{d.nameL} *</div>
          <input
            type="text"
            className="field"
            placeholder="ej. Retiro de producto del mercado"
            value={topicName}
            onChange={(e) => setTopicName(e.target.value)}
            style={{ marginBottom: '16px' }}
          />

          <div className="label">{d.ctxL} *</div>
          <textarea
            className="area"
            placeholder="Describe el contexto de la crisis, qué ocurrió y qué antecedentes debe manejar el vocero..."
            value={contextText}
            onChange={(e) => setContextText(e.target.value)}
            style={{ marginBottom: '16px', minHeight: '90px' }}
          />

          <div className="label">{d.opticL}</div>
          <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
            {opticsOptions.map((o) => (
              <button
                type="button"
                key={o}
                className={`pill ${selectedOptic === o ? 'on' : ''}`}
                style={{ cursor: 'pointer', border: 'none' }}
                onClick={() => setSelectedOptic(o)}
              >
                {o}
              </button>
            ))}
          </div>

          <div className="label">{d.pubL}</div>
          <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
            {audienceOptions.map((p) => (
              <button
                type="button"
                key={p}
                className={`pill ${selectedAudience === p ? 'on' : ''}`}
                style={{ cursor: 'pointer', border: 'none' }}
                onClick={() => setSelectedAudience(p)}
              >
                {p}
              </button>
            ))}
          </div>

          <div className="label">Idiomas disponibles</div>
          <div style={{ display: 'flex', gap: '8px' }}>
            {availableLanguages.map((lang) => (
              <button
                type="button"
                key={lang}
                className={`pill ${selectedLanguages.includes(lang) ? 'on' : ''}`}
                style={{ cursor: 'pointer', border: 'none' }}
                onClick={() => handleToggleLanguage(lang)}
                title="Haz clic para activar o desactivar este idioma"
              >
                {lang} {selectedLanguages.includes(lang) ? '✓' : ''}
              </button>
            ))}
          </div>
        </div>

        {/* Right Column: Key Messages & Red Lines */}
        <div className="col">
          <div className="label">{d.keyL} * ({keyMessages.length})</div>
          {keyMessages.length === 0 && (
            <div
              style={{
                fontSize: '12px',
                color: 'var(--muted)',
                fontStyle: 'italic',
                marginBottom: '10px'
              }}
            >
              No hay mensajes clave aún. Agrega al menos uno abajo.
            </div>
          )}
          {keyMessages.map((msg, i) => (
            <div
              key={i}
              className="box"
              style={{
                padding: '10px 12px',
                marginBottom: '8px',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                fontSize: '12.5px'
              }}
            >
              <span>{msg}</span>
              <button
                type="button"
                className="iconbtn"
                style={{ width: '22px', height: '22px', border: 'none', background: 'transparent', cursor: 'pointer' }}
                onClick={() => handleRemoveKey(i)}
                title="Eliminar mensaje"
              >
                ✕
              </button>
            </div>
          ))}

          <div style={{ display: 'flex', gap: '8px', marginBottom: '18px' }}>
            <input
              type="text"
              className="field"
              placeholder="Escribe un mensaje clave..."
              value={newKeyInput}
              onChange={(e) => setNewKeyInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  handleAddKey();
                }
              }}
            />
            <button
              type="button"
              className="btn ghost"
              onClick={handleAddKey}
              style={{ whiteSpace: 'nowrap' }}
            >
              {d.addMsg}
            </button>
          </div>

          <div className="label">{d.redL} ({redLines.length})</div>
          {redLines.length === 0 && (
            <div
              style={{
                fontSize: '12px',
                color: 'var(--muted)',
                fontStyle: 'italic',
                marginBottom: '10px'
              }}
            >
              Sin líneas rojas definidas aún.
            </div>
          )}
          {redLines.map((red, i) => (
            <div
              key={i}
              className="box"
              style={{
                padding: '10px 12px',
                marginBottom: '8px',
                borderColor: '#e0a3a3',
                background: 'rgba(224, 163, 163, 0.08)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                fontSize: '12.5px'
              }}
            >
              <span style={{ color: 'var(--danger)' }}>🚫 {red}</span>
              <button
                type="button"
                className="iconbtn"
                style={{ width: '22px', height: '22px', border: 'none', background: 'transparent', cursor: 'pointer' }}
                onClick={() => handleRemoveRed(i)}
                title="Eliminar línea roja"
              >
                ✕
              </button>
            </div>
          ))}

          <div style={{ display: 'flex', gap: '8px' }}>
            <input
              type="text"
              className="field"
              placeholder="Escribe una línea roja (lo que NUNCA debe decirse)..."
              value={newRedInput}
              onChange={(e) => setNewRedInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  handleAddRed();
                }
              }}
            />
            <button
              type="button"
              className="btn ghost"
              onClick={handleAddRed}
              style={{ whiteSpace: 'nowrap' }}
            >
              {d.addRed}
            </button>
          </div>
        </div>
      </div>

      {/* Action Buttons */}
      <div style={{ display: 'flex', gap: '12px', marginTop: '22px', alignItems: 'center' }}>
        <button
          type="button"
          className="btn pri"
          onClick={handleSave}
          disabled={isSaving}
          style={{ minWidth: '150px' }}
        >
          {isSaving ? 'Guardando...' : `💾 ${d.save}`}
        </button>
        <button
          type="button"
          className="btn ghost"
          onClick={() => onNavigate('a1')}
          disabled={isSaving}
        >
          Cancelar
        </button>
      </div>
    </div>
  );
};
