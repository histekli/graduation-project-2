import { useState, useCallback, useRef, useEffect } from "react";

const API_BASE = (
  (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_URL) ||
  "http://localhost:8000"
).replace(/\/+$/, "");

const REQUEST_TIMEOUT_MS = 90_000;

const SEV = {
  error:   { label: "Hata",  color: "#ef4444", bg: "rgba(239,68,68,0.08)",   border: "rgba(239,68,68,0.25)",   icon: "✕" },
  warning: { label: "Uyarı", color: "#f59e0b", bg: "rgba(245,158,11,0.08)",  border: "rgba(245,158,11,0.25)",  icon: "△" },
  info:    { label: "Bilgi", color: "#3b82f6",  bg: "rgba(59,130,246,0.08)",  border: "rgba(59,130,246,0.25)",  icon: "○" },
};

const LAYER_LABELS = { A: "Kural Motoru", B: "RAG Kontrol", C: "Semantik Analiz" };

// ── GTU Emblem ────────────────────────────────────────────────────────────────

function GTUEmblem({ size = 40 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 60 60" fill="none" xmlns="http://www.w3.org/2000/svg">
      <polygon points="30,2 56,16 56,44 30,58 4,44 4,16" fill="var(--accent)" />
      <polygon points="30,8 50,19 50,41 30,52 10,41 10,19" fill="none" stroke="rgba(255,255,255,0.3)" strokeWidth="1" />
      <text x="30" y="38" textAnchor="middle" fontSize="15" fontWeight="900" fill="white"
        fontFamily="Arial, sans-serif" letterSpacing="-0.5">GTÜ</text>
    </svg>
  );
}

// ── HTTP helpers ──────────────────────────────────────────────────────────────

async function analyzeDocument(file, mode, signal) {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/analyze?mode=${encodeURIComponent(mode)}`, {
    method: "POST", body: formData, signal,
  });
  if (!res.ok) {
    let detail = `Sunucu hatası (HTTP ${res.status})`;
    try { const b = await res.json(); if (b.detail) detail = b.detail; } catch { try { detail = await res.text(); } catch { } }
    throw new Error(detail);
  }
  return res.json();
}

// ── StatusDot ─────────────────────────────────────────────────────────────────

function StatusDot({ active, loading, pulse }) {
  if (loading) return (
    <span style={{
      display: "inline-block", width: 8, height: 8, borderRadius: "50%",
      border: "1.5px solid var(--border-strong)", borderTopColor: "var(--text-muted)",
      animation: "spin 0.8s linear infinite",
    }} />
  );
  return (
    <span style={{
      display: "inline-block", width: 8, height: 8, borderRadius: "50%",
      background: active === "ok"      ? "#22c55e" :
                  active === "warning" ? "#f59e0b" :
                  active === false     ? "#ef4444" : "var(--text-muted)",
      boxShadow: (active === "ok" && pulse) ? "0 0 0 3px rgba(34,197,94,0.2)" : "none",
      flexShrink: 0,
    }} />
  );
}

// ── SystemStatus ──────────────────────────────────────────────────────────────

function SystemStatus() {
  const [status, setStatus]           = useState(null);
  const [backendOk, setBackendOk]     = useState(null);
  const [apiCheck, setApiCheck]       = useState(null);
  const [checking, setChecking]       = useState(false);
  const [expanded, setExpanded]       = useState(false);
  const [showKeyForm, setShowKeyForm] = useState(false);
  const [keyInput, setKeyInput]       = useState("");
  const [providerInput, setProvider]  = useState("gemini");
  const [saving, setSaving]           = useState(false);
  const [saveResult, setSaveResult]   = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/status`, { signal: AbortSignal.timeout(5000) });
        if (!res.ok) throw new Error();
        const data = await res.json();
        if (!cancelled) { setStatus(data); setBackendOk(true); }
      } catch { if (!cancelled) setBackendOk(false); }
    })();
    return () => { cancelled = true; };
  }, []);

  const testApiKey = useCallback(async () => {
    setChecking(true); setApiCheck(null);
    try {
      const res = await fetch(`${API_BASE}/check-api-key`, { signal: AbortSignal.timeout(20000) });
      const data = await res.json();
      setApiCheck(data);
    } catch { setApiCheck({ ok: false, error: "Sunucuya ulaşılamadı", error_type: "network" }); }
    finally { setChecking(false); }
  }, []);

  const saveApiKey = useCallback(async () => {
    if (!keyInput.trim()) return;
    setSaving(true); setSaveResult(null);
    try {
      const res = await fetch(`${API_BASE}/admin/set-api-key`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider: providerInput, api_key: keyInput.trim() }),
        signal: AbortSignal.timeout(25000),
      });
      const data = await res.json();
      if (!res.ok) {
        setSaveResult({ ok: false, error: data.detail || "Kaydetme başarısız" });
      } else {
        setSaveResult({ ok: true, message: data.message });
        setKeyInput(""); setShowKeyForm(false);
        const sr = await fetch(`${API_BASE}/status`).then(r => r.json()).catch(() => null);
        if (sr) setStatus(sr);
        setApiCheck(null);
      }
    } catch { setSaveResult({ ok: false, error: "Sunucuya ulaşılamadı" }); }
    finally { setSaving(false); }
  }, [keyInput, providerInput]);

  const layers = status?.layers;
  const layerC = layers?.C;

  let apiKeyState = "unknown";
  if (apiCheck) {
    if (apiCheck.ok) apiKeyState = "ok";
    else if (apiCheck.error_type === "quota_exceeded") apiKeyState = "warning";
    else apiKeyState = false;
  } else if (layerC) {
    if (layerC.quota_state === "quota_exceeded") apiKeyState = "warning";
    else apiKeyState = layerC.active ? "ok" : false;
  }

  const apiKeyLabel =
    apiCheck?.ok                              ? `Aktif — ${apiCheck.provider}/${apiCheck.model}` :
    apiCheck?.error_type === "quota_exceeded" ? "Kota dolmuş — anahtar geçerli, limit bitti" :
    apiCheck?.error_type === "invalid_key"    ? "Geçersiz anahtar" :
    apiCheck?.error_type === "no_key"         ? "Yapılandırılmamış" :
    apiCheck?.error                           ? apiCheck.error.slice(0, 60) :
    layerC?.quota_state === "quota_exceeded"  ? "Kota dolmuş — anahtar geçerli, limit bitti" :
    layerC?.active                            ? `Yapılandırılmış — ${layerC.provider}/${layerC.model}` :
    layerC                                    ? "Yapılandırılmamış" : "—";

  return (
    <div style={{
      background: "var(--bg-card-subtle)",
      border: "1px solid var(--border-default)",
      borderRadius: 12, overflow: "hidden",
    }}>
      <button
        onClick={() => setExpanded(v => !v)}
        style={{
          width: "100%", padding: "12px 16px",
          display: "flex", alignItems: "center", justifyContent: "space-between",
          background: "none", border: "none", cursor: "pointer", color: "inherit",
          fontFamily: "inherit",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <StatusDot active={backendOk === null ? "unknown" : backendOk ? "ok" : false} loading={backendOk === null} pulse />
          <span style={{ fontSize: 12, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.04em" }}>
            SİSTEM DURUMU
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {["A","B","C"].map(k => (
            <span key={k} style={{
              fontSize: 10, padding: "2px 7px", borderRadius: 4, fontWeight: 600,
              fontFamily: "monospace",
              background: layers?.[k]?.active ? "rgba(34,197,94,0.1)" : backendOk === false ? "rgba(239,68,68,0.1)" : "var(--bg-card-subtle)",
              color:      layers?.[k]?.active ? "#4ade80"             : backendOk === false ? "#f87171"            : "var(--text-muted)",
              border: `1px solid ${layers?.[k]?.active ? "rgba(34,197,94,0.2)" : backendOk === false ? "rgba(239,68,68,0.2)" : "var(--border-default)"}`,
            }}>
              {k}
            </span>
          ))}
          <span style={{ fontSize: 14, color: "var(--text-muted)", transition: "transform 0.2s", transform: expanded ? "rotate(180deg)" : "none" }}>▾</span>
        </div>
      </button>

      {expanded && (
        <div style={{ padding: "0 16px 16px", display: "flex", flexDirection: "column", gap: 10 }}>
          {/* Backend */}
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            padding: "10px 12px", borderRadius: 8,
            background: backendOk ? "rgba(34,197,94,0.05)" : backendOk === false ? "rgba(239,68,68,0.05)" : "var(--bg-card-subtle)",
            border: `1px solid ${backendOk ? "rgba(34,197,94,0.15)" : backendOk === false ? "rgba(239,68,68,0.15)" : "var(--border-default)"}`,
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <StatusDot active={backendOk === null ? "unknown" : backendOk ? "ok" : false} loading={backendOk === null} />
              <span style={{ fontSize: 12, color: "var(--text-secondary)", fontWeight: 600 }}>Backend</span>
            </div>
            <span style={{ fontSize: 11, color: backendOk ? "#4ade80" : backendOk === false ? "#f87171" : "var(--text-muted)", fontFamily: "monospace" }}>
              {backendOk === null ? "bağlanıyor…" : backendOk ? `${API_BASE} ✓` : `${API_BASE} — ulaşılamıyor`}
            </span>
          </div>

          {/* Katman A + B */}
          {[
            { key: "A", icon: "⚙", color: "#a78bfa" },
            { key: "B", icon: "🗄", color: "#38bdf8" },
          ].map(({ key, color }) => (
            <div key={key} style={{
              display: "flex", alignItems: "center", justifyContent: "space-between",
              padding: "9px 12px", borderRadius: 8,
              background: "var(--bg-card-subtle)", border: "1px solid var(--border-default)",
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <StatusDot active={layers?.[key]?.active ? "ok" : layers ? false : "unknown"} loading={!layers} />
                <span style={{ fontSize: 12, color, fontWeight: 700, fontFamily: "monospace" }}>Katman {key}</span>
                <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{LAYER_LABELS[key]}</span>
              </div>
              <span style={{ fontSize: 11, color: layers?.[key]?.active ? "#4ade80" : "#f87171", fontFamily: "monospace" }}>
                {layers ? (layers[key]?.active ? layers[key].detail : layers[key]?.detail) : "—"}
              </span>
            </div>
          ))}

          {/* Katman C */}
          <div style={{
            padding: "10px 12px", borderRadius: 8,
            background: "var(--bg-card-subtle)",
            border: `1px solid ${
              apiKeyState === "ok"      ? "rgba(34,197,94,0.2)"  :
              apiKeyState === "warning" ? "rgba(245,158,11,0.2)" :
              apiKeyState === false     ? "rgba(239,68,68,0.2)"  : "var(--border-default)"
            }`,
          }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <StatusDot active={apiKeyState} loading={checking} />
                <span style={{ fontSize: 12, color: "var(--accent)", fontWeight: 700, fontFamily: "monospace" }}>Katman C</span>
                <span style={{ fontSize: 11, color: "var(--text-muted)" }}>Semantik Analiz (LLM)</span>
              </div>
              <span style={{
                fontSize: 11, fontFamily: "monospace",
                color: apiKeyState === "ok" ? "#4ade80" : apiKeyState === "warning" ? "#fbbf24" : apiKeyState === false ? "#f87171" : "var(--text-muted)",
              }}>
                {checking ? "test ediliyor…" : apiKeyLabel}
              </span>
            </div>

            <div style={{ display: "flex", gap: 6 }}>
              <button
                onClick={testApiKey}
                disabled={checking || !backendOk}
                style={{
                  flex: 1, padding: "8px 0", borderRadius: 7,
                  background: checking ? "var(--bg-card-subtle)" : "var(--accent-subtle)",
                  border: `1px solid ${checking ? "var(--border-default)" : "var(--accent-border)"}`,
                  color: checking || !backendOk ? "var(--text-muted)" : "var(--accent)",
                  fontSize: 12, fontWeight: 600, cursor: checking || !backendOk ? "not-allowed" : "pointer",
                  fontFamily: "inherit", transition: "all 0.2s",
                  display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
                }}
              >
                {checking
                  ? <><span style={{ width: 12, height: 12, border: "1.5px solid var(--border-strong)", borderTopColor: "var(--text-muted)", borderRadius: "50%", animation: "spin 0.8s linear infinite", display: "inline-block" }} />Test ediliyor…</>
                  : "🔑 Test Et"
                }
              </button>
              <button
                onClick={() => { setShowKeyForm(v => !v); setSaveResult(null); }}
                disabled={!backendOk}
                style={{
                  flex: 1, padding: "8px 0", borderRadius: 7,
                  background: showKeyForm ? "rgba(99,102,241,0.1)" : "var(--bg-card-subtle)",
                  border: `1px solid ${showKeyForm ? "rgba(99,102,241,0.3)" : "var(--border-default)"}`,
                  color: !backendOk ? "var(--text-muted)" : showKeyForm ? "#818cf8" : "var(--text-secondary)",
                  fontSize: 12, fontWeight: 600, cursor: !backendOk ? "not-allowed" : "pointer",
                  fontFamily: "inherit", transition: "all 0.2s",
                }}
              >
                ✏️ Anahtarı Değiştir
              </button>
            </div>

            {apiCheck && !showKeyForm && (
              <div style={{
                marginTop: 6, padding: "10px 12px", borderRadius: 6, fontSize: 11,
                background: apiCheck.ok ? "rgba(34,197,94,0.06)" : apiCheck.error_type === "quota_exceeded" ? "rgba(245,158,11,0.06)" : "rgba(239,68,68,0.06)",
                color: apiCheck.ok ? "#16a34a" : apiCheck.error_type === "quota_exceeded" ? "#d97706" : "#dc2626",
                lineHeight: 1.6,
              }}>
                <div style={{ fontFamily: "monospace" }}>
                  {apiCheck.ok ? `✓ Bağlantı başarılı — "${apiCheck.response_preview}"` : `✗ ${apiCheck.error}`}
                </div>
                {apiCheck.tip && (
                  <div style={{ marginTop: 6, color: "var(--text-muted)", fontSize: 10, lineHeight: 1.6 }}>
                    💡 {apiCheck.tip}
                  </div>
                )}
              </div>
            )}

            {showKeyForm && (
              <div style={{
                marginTop: 6, padding: "12px", borderRadius: 8,
                background: "rgba(99,102,241,0.05)", border: "1px solid rgba(99,102,241,0.15)",
                display: "flex", flexDirection: "column", gap: 8,
              }}>
                <div style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 600, letterSpacing: "0.04em" }}>SAĞLAYICI</div>
                <div style={{ display: "flex", gap: 6 }}>
                  {["gemini", "groq"].map(p => (
                    <button key={p} onClick={() => setProvider(p)} style={{
                      flex: 1, padding: "6px 0", borderRadius: 6,
                      background: providerInput === p ? "rgba(99,102,241,0.15)" : "var(--bg-card-subtle)",
                      border: `1px solid ${providerInput === p ? "rgba(99,102,241,0.4)" : "var(--border-default)"}`,
                      color: providerInput === p ? "#818cf8" : "var(--text-muted)",
                      fontSize: 11, fontWeight: 700, cursor: "pointer", fontFamily: "monospace",
                      transition: "all 0.15s",
                    }}>
                      {p === "gemini" ? "Google Gemini" : "Groq / Llama"}
                    </button>
                  ))}
                </div>
                <div style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 600, letterSpacing: "0.04em", marginTop: 2 }}>API ANAHTARI</div>
                <input
                  type="password"
                  value={keyInput}
                  onChange={e => setKeyInput(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && saveApiKey()}
                  placeholder={providerInput === "gemini" ? "AIzaSy…" : "gsk_…"}
                  style={{
                    padding: "9px 12px", borderRadius: 7, fontSize: 12,
                    background: "var(--input-bg)", border: "1px solid var(--input-border)",
                    color: "var(--text-primary)", outline: "none", fontFamily: "monospace",
                    letterSpacing: "0.05em",
                  }}
                />
                <div style={{ fontSize: 10, color: "var(--text-muted)", lineHeight: 1.5 }}>
                  {providerInput === "gemini"
                    ? "aistudio.google.com/app/apikey adresinden ücretsiz alınabilir"
                    : "console.groq.com adresinden ücretsiz alınabilir"}
                </div>
                <div style={{ display: "flex", gap: 6 }}>
                  <button
                    onClick={saveApiKey}
                    disabled={saving || !keyInput.trim()}
                    style={{
                      flex: 1, padding: "9px 0", borderRadius: 7,
                      background: saving || !keyInput.trim() ? "var(--bg-card-subtle)" : "linear-gradient(135deg, #6366f1, #4f46e5)",
                      border: "none", color: saving || !keyInput.trim() ? "var(--text-muted)" : "#fff",
                      fontSize: 12, fontWeight: 700, cursor: saving || !keyInput.trim() ? "not-allowed" : "pointer",
                      fontFamily: "inherit", display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
                    }}
                  >
                    {saving
                      ? <><span style={{ width: 12, height: 12, border: "1.5px solid rgba(165,180,252,0.3)", borderTopColor: "#a5b4fc", borderRadius: "50%", animation: "spin 0.8s linear infinite", display: "inline-block" }} />Kaydediliyor…</>
                      : "✓ Kaydet ve Etkinleştir"
                    }
                  </button>
                  <button
                    onClick={() => { setShowKeyForm(false); setKeyInput(""); setSaveResult(null); }}
                    style={{
                      padding: "9px 14px", borderRadius: 7, background: "var(--bg-card-subtle)",
                      border: "1px solid var(--border-default)", color: "var(--text-muted)",
                      fontSize: 12, cursor: "pointer", fontFamily: "inherit",
                    }}
                  >
                    İptal
                  </button>
                </div>
                {saveResult && (
                  <div style={{
                    padding: "8px 10px", borderRadius: 6, fontSize: 11, fontFamily: "monospace",
                    background: saveResult.ok ? "rgba(34,197,94,0.08)" : "rgba(239,68,68,0.08)",
                    color: saveResult.ok ? "#16a34a" : "#dc2626", lineHeight: 1.5,
                  }}>
                    {saveResult.ok ? `✓ ${saveResult.message}` : `✗ ${saveResult.error}`}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ── StatCard ──────────────────────────────────────────────────────────────────

function StatCard({ label, value, color, icon, delay }) {
  return (
    <div style={{
      background: "var(--bg-card)", border: `1px solid ${color}22`,
      borderRadius: 12, padding: "18px 22px", flex: 1, minWidth: 130,
      boxShadow: "var(--shadow-card)",
      animation: `fadeSlideUp 0.5s ease ${delay}s both`,
    }}>
      <div style={{ fontSize: 13, color: "var(--text-secondary)", letterSpacing: "0.04em", marginBottom: 6 }}>{label}</div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
        <span style={{ fontSize: 32, fontWeight: 700, color, fontFamily: "'JetBrains Mono', monospace" }}>{value}</span>
        <span style={{ fontSize: 16, color: color + "88" }}>{icon}</span>
      </div>
    </div>
  );
}

// ── FindingCard ───────────────────────────────────────────────────────────────

function FindingCard({ finding, index }) {
  const [open, setOpen] = useState(false);
  const sev = SEV[finding.severity] ?? SEV.info;

  return (
    <div
      onClick={() => setOpen(!open)}
      style={{
        background: open ? sev.bg : "var(--bg-card)",
        border: `1px solid ${open ? sev.border : "var(--border-default)"}`,
        borderRadius: 10, padding: "14px 18px", cursor: "pointer",
        transition: "all 0.2s ease", boxShadow: "var(--shadow-card)",
        animation: `fadeSlideUp 0.4s ease ${0.04 * Math.min(index, 12)}s both`,
      }}
      onMouseEnter={e => { e.currentTarget.style.borderColor = sev.border; e.currentTarget.style.background = sev.bg; }}
      onMouseLeave={e => { if (!open) { e.currentTarget.style.borderColor = "var(--border-default)"; e.currentTarget.style.background = "var(--bg-card)"; }}}
    >
      <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
        <div style={{
          width: 28, height: 28, borderRadius: 8,
          background: sev.bg, border: `1px solid ${sev.border}`,
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 13, color: sev.color, fontWeight: 700, flexShrink: 0, marginTop: 1,
        }}>{sev.icon}</div>

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <span style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)" }}>{finding.title}</span>
            <span style={{
              fontSize: 10, padding: "2px 7px", borderRadius: 4,
              background: sev.bg, color: sev.color, fontWeight: 600,
              border: `1px solid ${sev.border}`, fontFamily: "monospace",
            }}>{finding.rule_code}</span>
            <span style={{
              fontSize: 10, padding: "2px 7px", borderRadius: 4,
              background: "var(--accent-subtle)", color: "var(--accent)",
              border: "1px solid var(--accent-border)", fontFamily: "monospace",
            }}>Katman {finding.layer}</span>
          </div>
          <p style={{ fontSize: 13, color: "var(--text-secondary)", margin: "6px 0 0", lineHeight: 1.5 }}>
            {finding.description}
          </p>

          {open && (
            <div style={{
              marginTop: 14, paddingTop: 14,
              borderTop: "1px solid var(--border-default)",
              display: "flex", flexDirection: "column", gap: 10,
            }}>
              {finding.found && (
                <div style={{ display: "flex", gap: 8 }}>
                  <span style={{ fontSize: 12, color: "var(--text-muted)", minWidth: 70 }}>Bulunan:</span>
                  <code style={{ fontSize: 12, color: "#ef4444", background: "rgba(239,68,68,0.08)", padding: "2px 8px", borderRadius: 4, fontFamily: "'JetBrains Mono', monospace" }}>{finding.found}</code>
                </div>
              )}
              {finding.expected && (
                <div style={{ display: "flex", gap: 8 }}>
                  <span style={{ fontSize: 12, color: "var(--text-muted)", minWidth: 70 }}>Beklenen:</span>
                  <code style={{ fontSize: 12, color: "#16a34a", background: "rgba(22,163,74,0.08)", padding: "2px 8px", borderRadius: 4, fontFamily: "'JetBrains Mono', monospace" }}>{finding.expected}</code>
                </div>
              )}
              {finding.location?.text_snippet && (
                <div style={{ display: "flex", gap: 8 }}>
                  <span style={{ fontSize: 12, color: "var(--text-muted)", minWidth: 70 }}>Konum:</span>
                  <code style={{ fontSize: 11, color: "var(--text-secondary)", background: "var(--bg-card-subtle)", padding: "2px 8px", borderRadius: 4, fontFamily: "'JetBrains Mono', monospace" }}>
                    {finding.location.section && `[${finding.location.section}] `}{finding.location.text_snippet}
                  </code>
                </div>
              )}
              {finding.reference && (
                <div style={{ display: "flex", gap: 8 }}>
                  <span style={{ fontSize: 12, color: "var(--text-muted)", minWidth: 70 }}>Referans:</span>
                  <span style={{ fontSize: 12, color: "var(--accent)" }}>{finding.reference}</span>
                </div>
              )}
              {finding.suggestion && (
                <div style={{ marginTop: 4, padding: "10px 14px", background: "rgba(22,163,74,0.06)", border: "1px solid rgba(22,163,74,0.15)", borderRadius: 8, fontSize: 12, color: "#16a34a", lineHeight: 1.5 }}>
                  💡 {finding.suggestion}
                </div>
              )}
              {finding.suggested_text && (
                <div style={{ marginTop: 2, padding: "12px 14px", background: "var(--accent-subtle)", border: "1px solid var(--accent-border)", borderRadius: 8, lineHeight: 1.6 }}>
                  <div style={{ fontSize: 10, fontWeight: 700, color: "var(--accent)", letterSpacing: "0.06em", marginBottom: 6 }}>
                    ✦ YAPAY ZEKA YENİDEN YAZIM ÖNERİSİ
                  </div>
                  <div style={{ fontSize: 12, color: "var(--text-primary)", fontStyle: "italic" }}>
                    "{finding.suggested_text}"
                  </div>
                </div>
              )}
              {finding.confidence < 1.0 && (
                <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                  Güven skoru: {Math.round(finding.confidence * 100)}%
                </div>
              )}
            </div>
          )}
        </div>

        <div style={{ color: "var(--text-muted)", fontSize: 16, transition: "transform 0.2s", transform: open ? "rotate(180deg)" : "rotate(0deg)", flexShrink: 0 }}>▾</div>
      </div>
    </div>
  );
}

// ── ErrorBanner ───────────────────────────────────────────────────────────────

function ErrorBanner({ message, onDismiss }) {
  return (
    <div style={{
      display: "flex", alignItems: "flex-start", gap: 12,
      padding: "14px 16px", borderRadius: 10,
      background: "rgba(239,68,68,0.07)", border: "1px solid rgba(239,68,68,0.25)",
      animation: "fadeSlideUp 0.3s ease both",
    }}>
      <span style={{ color: "#ef4444", fontSize: 16, flexShrink: 0, marginTop: 1 }}>✕</span>
      <div style={{ flex: 1, fontSize: 13, color: "#dc2626", lineHeight: 1.55 }}>{message}</div>
      <button onClick={onDismiss} style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer", fontSize: 16, padding: 0, flexShrink: 0 }}>✕</button>
    </div>
  );
}

// ── Pipeline steps ────────────────────────────────────────────────────────────

const PIPELINE_STEPS = [
  { n: 1, label: "Belge ayrıştırılıyor",        desc: ".docx okuma · bölüm ve alan tespiti" },
  { n: 2, label: "Kural motoru çalışıyor",       desc: "Biçim · zorunlu alanlar · tutarlılık" },
  { n: 3, label: "Kılavuz veritabanı taranıyor", desc: "TDK vektör araması · RAG eşleştirme" },
  { n: 4, label: "Yapay zeka değerlendiriyor",   desc: "Semantik analiz · LLM bulgular · öneriler" },
  { n: 5, label: "Rapor hazırlanıyor",            desc: "Tüm bulgular derlendi" },
];

const STEP_DELAYS    = [1400, 2200, 3500];

const DOWNLOAD_STEPS = [
  { n: 1, label: "Belge yeniden analiz ediliyor",  desc: "Düzeltilecek konumlar belirleniyor" },
  { n: 2, label: "Hatalar otomatik düzeltiliyor",  desc: "Font · boşluk · yazım · kapanış" },
  { n: 3, label: "İndirme dosyası hazırlanıyor",   desc: "Düzeltilmiş .docx oluşturuluyor" },
];
const DOWNLOAD_STEP_DELAYS = [2000, 4000];

// ── Main App ──────────────────────────────────────────────────────────────────

export default function App() {
  const [isDark, setIsDark]           = useState(false);
  const [file, setFile]               = useState(null);
  const [dragOver, setDragOver]       = useState(false);
  const [analyzing, setAnalyzing]     = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [results, setResults]         = useState(null);
  const [error, setError]             = useState(null);
  const [mode, setMode]               = useState("full");
  const [priority, setPriority]       = useState("all");
  const [currentStep, setCurrentStep]     = useState(0);
  const [downloadStep, setDownloadStep]   = useState(0);
  const inputRef       = useRef(null);
  const abortRef       = useRef(null);
  const stepTimers     = useRef([]);
  const downloadTimers = useRef([]);

  const handleFile = useCallback((f) => {
    if (!f) return;
    if (!f.name.endsWith(".docx")) { setError("Sadece .docx dosyaları desteklenmektedir."); return; }
    if (f.size > 10 * 1024 * 1024) { setError("Dosya boyutu 10 MB sınırını aşıyor."); return; }
    setFile(f); setResults(null); setError(null);
  }, []);

  const handleDrop = useCallback((e) => { e.preventDefault(); setDragOver(false); handleFile(e.dataTransfer.files[0]); }, [handleFile]);

  const clearStepTimers = useCallback(() => {
    stepTimers.current.forEach(t => clearTimeout(t));
    stepTimers.current = [];
  }, []);

  const startAnalysis = useCallback(async () => {
    if (!file || analyzing) return;
    setAnalyzing(true); setError(null); setResults(null);
    setCurrentStep(1);
    clearStepTimers();
    let acc = 0;
    stepTimers.current = STEP_DELAYS.map((delay, i) => {
      acc += delay;
      return setTimeout(() => setCurrentStep(i + 2), acc);
    });
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const tid = setTimeout(() => controller.abort("timeout"), REQUEST_TIMEOUT_MS);
    try {
      const data = await analyzeDocument(file, mode, controller.signal);
      clearStepTimers();
      setCurrentStep(5);
      setResults(data);
    } catch (err) {
      clearStepTimers();
      setCurrentStep(0);
      if (err.name === "AbortError" || err.message === "timeout") {
        setError(`İstek zaman aşımına uğradı (${REQUEST_TIMEOUT_MS / 1000}s). Backend çalışıyor mu?`);
      } else if (err.message?.includes("Failed to fetch") || err.message?.includes("NetworkError")) {
        setError(`Backend'e bağlanılamadı. ${API_BASE} adresinde uvicorn çalıştığından emin olun.`);
      } else {
        setError(err.message || "Bilinmeyen bir hata oluştu.");
      }
    } finally { clearTimeout(tid); setAnalyzing(false); }
  }, [file, mode, analyzing, clearStepTimers]);

  const cancelAnalysis = useCallback(() => {
    clearStepTimers(); setCurrentStep(0);
    abortRef.current?.abort();
    setAnalyzing(false); setError(null);
  }, [clearStepTimers]);

  const clearDownloadTimers = useCallback(() => {
    downloadTimers.current.forEach(t => clearTimeout(t));
    downloadTimers.current = [];
  }, []);

  const downloadFixed = useCallback(async () => {
    if (!file || !results || downloading) return;
    setDownloading(true); setError(null);
    setDownloadStep(1);
    clearDownloadTimers();
    let acc = 0;
    downloadTimers.current = DOWNLOAD_STEP_DELAYS.map((delay, i) => {
      acc += delay;
      return setTimeout(() => setDownloadStep(i + 2), acc);
    });
    const controller = new AbortController();
    const tid = setTimeout(() => controller.abort("timeout"), REQUEST_TIMEOUT_MS);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch(`${API_BASE}/analyze-and-fix?mode=${encodeURIComponent(mode)}`, { method: "POST", body: formData, signal: controller.signal });
      if (!res.ok) { let d = `HTTP ${res.status}`; try { const j = await res.json(); d = j.detail || d; } catch { } throw new Error(d); }
      const blob = await res.blob();
      clearDownloadTimers(); setDownloadStep(0);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `${file.name.replace(/\.docx$/i, "")}_duzeltilmis.docx`;
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      clearDownloadTimers(); setDownloadStep(0);
      if (err.name === "AbortError" || err.message === "timeout") setError("İndirme zaman aşımına uğradı.");
      else if (err.message?.includes("Failed to fetch")) setError(`Backend'e bağlanılamadı.`);
      else setError(err.message || "İndirme sırasında hata oluştu.");
    } finally { clearTimeout(tid); setDownloading(false); }
  }, [file, mode, results, downloading, clearDownloadTimers]);

  const filteredFindings = (results?.findings ?? []).filter(f => priority === "all" || f.severity === priority);

  const pipelineSteps = PIPELINE_STEPS.map((s, i) => {
    let status = "pending";
    if (results) { status = "done"; }
    else if (analyzing) {
      if (i + 1 < currentStep) status = "done";
      else if (i + 1 === currentStep) status = "active";
    }
    return { ...s, status };
  });

  const score = results?.compliance_score;
  const scoreColor = score >= 80 ? "#16a34a" : score >= 60 ? "#d97706" : "#dc2626";

  return (
    <div
      data-theme={isDark ? "dark" : "light"}
      style={{ minHeight: "100vh", background: "var(--bg-page)", color: "var(--text-primary)", fontFamily: "'DM Sans', -apple-system, sans-serif" }}
    >
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap');

        [data-theme="light"] {
          --bg-page: #F5F4F0;
          --bg-card: #FFFFFF;
          --bg-card-subtle: rgba(0,0,0,0.02);
          --bg-card-hover: rgba(0,0,0,0.03);
          --border-default: rgba(0,0,0,0.09);
          --border-strong: rgba(0,0,0,0.15);
          --border-subtle: rgba(0,0,0,0.05);
          --text-primary: #18182A;
          --text-secondary: #50506E;
          --text-muted: #8080A0;
          --text-placeholder: #AAAABB;
          --accent: #E85200;
          --accent-hover: #CC4800;
          --accent-subtle: rgba(232,82,0,0.08);
          --accent-border: rgba(232,82,0,0.22);
          --header-bg: rgba(255,255,255,0.92);
          --header-border: rgba(0,0,0,0.08);
          --input-bg: #FFFFFF;
          --input-border: rgba(0,0,0,0.12);
          --shadow-card: 0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
          --shadow-header: 0 1px 0 rgba(0,0,0,0.08);
          --scrollbar-thumb: #D0D0C8;
          --upload-border: rgba(0,0,0,0.12);
          --upload-border-hover: #E85200;
          --score-track: rgba(0,0,0,0.06);
        }

        [data-theme="dark"] {
          --bg-page: #0A0E17;
          --bg-card: rgba(255,255,255,0.025);
          --bg-card-subtle: rgba(255,255,255,0.015);
          --bg-card-hover: rgba(255,255,255,0.04);
          --border-default: rgba(255,255,255,0.07);
          --border-strong: rgba(255,255,255,0.12);
          --border-subtle: rgba(255,255,255,0.04);
          --text-primary: #E2E8F0;
          --text-secondary: #94A3B8;
          --text-muted: #475569;
          --text-placeholder: #334155;
          --accent: #F07030;
          --accent-hover: #FF8040;
          --accent-subtle: rgba(240,112,48,0.10);
          --accent-border: rgba(240,112,48,0.25);
          --header-bg: rgba(10,14,23,0.88);
          --header-border: rgba(255,255,255,0.06);
          --input-bg: rgba(255,255,255,0.04);
          --input-border: rgba(255,255,255,0.10);
          --shadow-card: none;
          --shadow-header: none;
          --scrollbar-thumb: #1E293B;
          --upload-border: rgba(255,255,255,0.08);
          --upload-border-hover: #F07030;
          --score-track: rgba(255,255,255,0.06);
        }

        @keyframes fadeSlideUp { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes pulse { 0%, 100% { opacity: 0.4; } 50% { opacity: 1; } }
        @keyframes spin { to { transform: rotate(360deg); } }
        * { box-sizing: border-box; }
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: var(--scrollbar-thumb); border-radius: 3px; }
        button:hover:not(:disabled) { opacity: 0.88; }
        select option { background: var(--bg-page); color: var(--text-primary); }
      `}</style>

      {/* ── Header ── */}
      <header style={{
        borderBottom: "1px solid var(--header-border)",
        padding: "0 32px",
        height: 64,
        display: "flex", alignItems: "center", justifyContent: "space-between",
        background: "var(--header-bg)",
        backdropFilter: "blur(14px)",
        boxShadow: "var(--shadow-header)",
        position: "sticky", top: 0, zIndex: 10,
      }}>
        {/* Logo + Title */}
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <GTUEmblem size={40} />
          <div>
            <div style={{ fontSize: 10, color: "var(--accent)", letterSpacing: "0.10em", fontWeight: 700, textTransform: "uppercase" }}>
              Gebze Teknik Üniversitesi
            </div>
            <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.01em", lineHeight: 1.2 }}>
              Yazışma Uyum Denetleyicisi
            </div>
          </div>
        </div>

        {/* Right side: version + theme toggle */}
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{
            padding: "4px 12px", borderRadius: 20,
            background: "var(--accent-subtle)", border: "1px solid var(--accent-border)",
            fontSize: 11, color: "var(--accent)", fontWeight: 700, fontFamily: "monospace",
          }}>v0.6</span>

          <button
            onClick={() => setIsDark(v => !v)}
            title={isDark ? "Açık temaya geç" : "Koyu temaya geç"}
            style={{
              width: 38, height: 38, borderRadius: 10,
              background: "var(--bg-card-subtle)", border: "1px solid var(--border-default)",
              color: "var(--text-secondary)", fontSize: 17, cursor: "pointer",
              display: "flex", alignItems: "center", justifyContent: "center",
              transition: "all 0.2s",
            }}
          >
            {isDark ? "☀️" : "🌙"}
          </button>
        </div>
      </header>

      {/* ── Main Layout ── */}
      <div style={{
        display: "grid",
        gridTemplateColumns: results ? "420px 1fr" : "1fr",
        maxWidth: 1280, margin: "0 auto", padding: "32px 24px", gap: 32,
        transition: "grid-template-columns 0.3s ease",
      }}>

        {/* ── Left Panel ── */}
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>

          <SystemStatus />

          {/* Upload area */}
          <div
            style={{
              background: dragOver ? "var(--accent-subtle)" : "var(--bg-card)",
              border: `2px dashed ${dragOver ? "var(--upload-border-hover)" : "var(--upload-border)"}`,
              borderRadius: 16, padding: 32, transition: "all 0.2s ease", cursor: "pointer",
              boxShadow: "var(--shadow-card)",
            }}
            onDragOver={e => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => inputRef.current?.click()}
          >
            <input ref={inputRef} type="file" accept=".docx" style={{ display: "none" }} onChange={e => handleFile(e.target.files[0])} />
            <div style={{ textAlign: "center" }}>
              <div style={{
                width: 56, height: 56, borderRadius: 14, margin: "0 auto 16px",
                background: "var(--accent-subtle)", border: "1px solid var(--accent-border)",
                display: "flex", alignItems: "center", justifyContent: "center", fontSize: 24,
              }}>📄</div>
              {file ? (
                <>
                  <div style={{ fontSize: 15, fontWeight: 600, color: "var(--text-primary)" }}>{file.name}</div>
                  <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>{(file.size / 1024).toFixed(1)} KB — Değiştirmek için tıklayın</div>
                </>
              ) : (
                <>
                  <div style={{ fontSize: 15, fontWeight: 600, color: "var(--text-secondary)" }}>Dosyayı seçin veya sürükleyip bırakın</div>
                  <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>.docx biçiminde, en fazla 10 MB</div>
                </>
              )}
            </div>
          </div>

          {/* Mode & Priority */}
          <div style={{ display: "flex", gap: 12 }}>
            {[
              { label: "MOD", value: mode, set: setMode, opts: [["full","Tam inceleme"],["format_only","Sadece biçim"],["content_only","Sadece içerik"]] },
              { label: "ÖNCELİK", value: priority, set: setPriority, opts: [["all","Tümü"],["error","Sadece hatalar"],["warning","Sadece uyarılar"],["info","Sadece bilgiler"]] },
            ].map(({ label, value, set, opts }) => (
              <div key={label} style={{ flex: 1 }}>
                <label style={{ fontSize: 11, color: "var(--text-muted)", display: "block", marginBottom: 6, fontWeight: 700, letterSpacing: "0.05em" }}>{label}</label>
                <select value={value} onChange={e => set(e.target.value)} disabled={analyzing} style={{
                  width: "100%", padding: "10px 14px", borderRadius: 10,
                  background: "var(--input-bg)", border: "1px solid var(--input-border)",
                  color: "var(--text-primary)", fontSize: 13, outline: "none",
                  cursor: analyzing ? "not-allowed" : "pointer", fontFamily: "inherit",
                  boxShadow: "var(--shadow-card)",
                }}>
                  {opts.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              </div>
            ))}
          </div>

          {/* Analyze / Cancel */}
          {analyzing ? (
            <button onClick={cancelAnalysis} style={{
              padding: "14px 24px", borderRadius: 12, border: "1px solid rgba(239,68,68,0.3)",
              background: "rgba(239,68,68,0.06)", color: "#ef4444",
              fontSize: 14, fontWeight: 600, cursor: "pointer", fontFamily: "inherit",
              display: "flex", alignItems: "center", justifyContent: "center", gap: 10,
            }}>
              <span style={{ width: 16, height: 16, border: "2px solid rgba(239,68,68,0.3)", borderTopColor: "#ef4444", borderRadius: "50%", animation: "spin 0.8s linear infinite", display: "inline-block" }} />
              İnceleniyor… (İptal et)
            </button>
          ) : (
            <button onClick={startAnalysis} disabled={!file} style={{
              padding: "14px 24px", borderRadius: 12, border: "none",
              background: file ? "linear-gradient(135deg, var(--accent) 0%, #B83E00 100%)" : "var(--bg-card-subtle)",
              color: file ? "#fff" : "var(--text-muted)",
              fontSize: 14, fontWeight: 700,
              cursor: file ? "pointer" : "not-allowed", fontFamily: "inherit", transition: "all 0.2s ease",
              boxShadow: file ? "0 4px 14px var(--accent-subtle)" : "none",
            }}>
              İncelemeyi Başlat
            </button>
          )}

          {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

          {/* Pipeline */}
          <div style={{
            background: "var(--bg-card)", border: "1px solid var(--border-default)",
            borderRadius: 12, padding: 20, boxShadow: "var(--shadow-card)",
          }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text-muted)", marginBottom: 14, letterSpacing: "0.03em" }}>İşlem Hattı</div>

            {analyzing && currentStep >= 1 && currentStep <= 4 && (() => {
              const step = PIPELINE_STEPS[currentStep - 1];
              const isLlm = currentStep === 4;
              return (
                <div style={{
                  marginBottom: 14, padding: "10px 14px", borderRadius: 8,
                  background: isLlm ? "var(--accent-subtle)" : "rgba(34,197,94,0.06)",
                  border: `1px solid ${isLlm ? "var(--accent-border)" : "rgba(34,197,94,0.2)"}`,
                  display: "flex", alignItems: "center", gap: 10,
                }}>
                  <span style={{
                    width: 14, height: 14, flexShrink: 0,
                    border: `2px solid ${isLlm ? "var(--accent-border)" : "rgba(34,197,94,0.3)"}`,
                    borderTopColor: isLlm ? "var(--accent)" : "#22c55e",
                    borderRadius: "50%", display: "inline-block",
                    animation: "spin 0.9s linear infinite",
                  }} />
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 700, color: isLlm ? "var(--accent)" : "#16a34a" }}>
                      {step.label}…
                    </div>
                    <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>
                      {isLlm ? "Bu adım 20–40 saniye sürebilir" : step.desc}
                    </div>
                  </div>
                </div>
              );
            })()}

            {pipelineSteps.map((step, i) => (
              <div key={i} style={{
                display: "flex", alignItems: "flex-start", gap: 10, padding: "7px 0",
                opacity: step.status === "pending" ? 0.35 : 1,
                transition: "opacity 0.3s ease",
              }}>
                <div style={{
                  width: 22, height: 22, borderRadius: 6, fontSize: 11, fontWeight: 700,
                  flexShrink: 0, marginTop: 1,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  background: step.status === "done"   ? "rgba(34,197,94,0.12)"
                             : step.status === "active" ? "var(--accent-subtle)"
                             : "var(--bg-card-subtle)",
                  color: step.status === "done"   ? "#16a34a"
                        : step.status === "active" ? "var(--accent)"
                        : "var(--text-muted)",
                  border: `1px solid ${step.status === "done"   ? "rgba(34,197,94,0.25)"
                                      : step.status === "active" ? "var(--accent-border)"
                                      : "var(--border-default)"}`,
                  ...(step.status === "active" ? { animation: "pulse 1.5s ease infinite" } : {}),
                }}>
                  {step.status === "done" ? "✓" : step.n}
                </div>
                <div>
                  <div style={{ fontSize: 12, fontWeight: 600, color: step.status === "done" ? "var(--text-muted)" : step.status === "active" ? "var(--text-primary)" : "var(--text-muted)" }}>
                    {step.label}
                  </div>
                  <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 1 }}>{step.desc}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* ── Right Panel: Results ── */}
        {results ? (
          <div style={{ animation: "fadeSlideUp 0.5s ease both" }}>
            <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 16, fontFamily: "'JetBrains Mono', monospace" }}>
              📄 {results.filename}
            </div>

            {/* Download button */}
            <div style={{ marginBottom: 24 }}>
              <button onClick={downloadFixed} disabled={downloading} style={{
                display: "flex", alignItems: "center", justifyContent: "center", gap: 10,
                width: "100%", padding: "13px 20px",
                borderRadius: downloading ? "10px 10px 0 0" : 10,
                border: "none",
                background: downloading ? "rgba(34,197,94,0.06)" : "linear-gradient(135deg, #22c55e 0%, #15803d 100%)",
                color: downloading ? "#16a34a" : "#fff",
                fontSize: 14, fontWeight: 700,
                cursor: downloading ? "not-allowed" : "pointer", fontFamily: "inherit",
                boxShadow: downloading ? "none" : "0 4px 14px rgba(34,197,94,0.22)",
                borderBottom: downloading ? "none" : undefined,
                transition: "all 0.2s",
              }}>
                {downloading ? (
                  <><span style={{ width: 16, height: 16, border: "2px solid rgba(22,163,74,0.3)", borderTopColor: "#16a34a", borderRadius: "50%", animation: "spin 0.8s linear infinite", display: "inline-block" }} />
                  {downloadStep >= 1 ? DOWNLOAD_STEPS[downloadStep - 1]?.label ?? "İndiriliyor…" : "Hazırlanıyor…"}…</>
                ) : (<><span style={{ fontSize: 18 }}>↓</span> Düzeltilmiş Belgeyi İndir</>)}
              </button>

              {downloading && (
                <div style={{
                  border: "1px solid rgba(34,197,94,0.2)", borderTop: "none",
                  borderRadius: "0 0 10px 10px",
                  background: "rgba(34,197,94,0.03)", padding: "10px 14px",
                  display: "flex", flexDirection: "column", gap: 6,
                }}>
                  {DOWNLOAD_STEPS.map((s, i) => {
                    const stepNum = i + 1;
                    const isDone = downloadStep > stepNum;
                    const isActive = downloadStep === stepNum;
                    return (
                      <div key={i} style={{
                        display: "flex", alignItems: "center", gap: 8,
                        opacity: !isDone && !isActive ? 0.3 : 1,
                        transition: "opacity 0.3s ease",
                      }}>
                        <div style={{
                          width: 18, height: 18, borderRadius: 5, flexShrink: 0,
                          display: "flex", alignItems: "center", justifyContent: "center",
                          fontSize: 10, fontWeight: 700,
                          background: isDone ? "rgba(34,197,94,0.12)" : isActive ? "rgba(34,197,94,0.10)" : "var(--bg-card-subtle)",
                          color: isDone ? "#16a34a" : isActive ? "#22c55e" : "var(--text-muted)",
                          border: `1px solid ${isDone ? "rgba(34,197,94,0.25)" : isActive ? "rgba(34,197,94,0.2)" : "var(--border-default)"}`,
                          ...(isActive ? { animation: "pulse 1.5s ease infinite" } : {}),
                        }}>
                          {isDone ? "✓" : s.n}
                        </div>
                        <div>
                          <div style={{ fontSize: 11, fontWeight: 600, color: isDone ? "var(--text-muted)" : isActive ? "#16a34a" : "var(--text-muted)" }}>
                            {s.label}
                          </div>
                          <div style={{ fontSize: 10, color: "var(--text-muted)" }}>{s.desc}</div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Stats */}
            <div style={{ display: "flex", gap: 14, marginBottom: 24, flexWrap: "wrap" }}>
              <StatCard label="Uyum Skoru" value={`${score}/100`} color={scoreColor} icon="★" delay={0.05} />
              <StatCard label="Toplam Bulgu" value={results.total_findings} color="var(--text-primary)" icon="◈" delay={0.1} />
              <StatCard label="Hata"   value={results.errors}   color="#ef4444" icon="✕" delay={0.2} />
              <StatCard label="Uyarı"  value={results.warnings} color="#f59e0b" icon="△" delay={0.3} />
              <StatCard label="Bilgi"  value={results.infos}    color="#3b82f6" icon="○" delay={0.4} />
            </div>

            {/* Score bar */}
            <div style={{ marginBottom: 20, padding: "14px 18px", background: "var(--bg-card)", borderRadius: 12, border: "1px solid var(--border-default)", boxShadow: "var(--shadow-card)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
                <span style={{ fontSize: 12, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.04em" }}>UYUM SKORU</span>
                <span style={{ fontSize: 13, fontWeight: 700, color: scoreColor }}>{score}/100</span>
              </div>
              <div style={{ height: 6, background: "var(--score-track)", borderRadius: 3, overflow: "hidden" }}>
                <div style={{
                  height: "100%", width: `${score}%`,
                  background: score >= 80 ? "#22c55e" : score >= 60 ? "#f59e0b" : "#ef4444",
                  borderRadius: 3, transition: "width 0.8s ease",
                }} />
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", marginTop: 6, fontSize: 10, color: "var(--text-muted)" }}>
                <span>Uyumsuz &lt;60</span><span>Orta 60–79</span><span>Uyumlu ≥80</span>
              </div>
            </div>

            {/* Layer breakdown */}
            <div style={{ display: "flex", gap: 8, marginBottom: 20, flexWrap: "wrap", animation: "fadeSlideUp 0.5s ease 0.3s both" }}>
              {["A","B","C"].map(layer => {
                const count = filteredFindings.filter(f => f.layer === layer).length;
                return (
                  <div key={layer} style={{
                    padding: "6px 14px", borderRadius: 8,
                    background: count > 0 ? "var(--accent-subtle)" : "var(--bg-card)",
                    border: `1px solid ${count > 0 ? "var(--accent-border)" : "var(--border-default)"}`,
                    fontSize: 12,
                    color: count > 0 ? "var(--accent)" : "var(--text-muted)",
                    boxShadow: "var(--shadow-card)",
                  }}>
                    <span style={{ fontWeight: 700 }}>Katman {layer}</span>
                    <span style={{ marginLeft: 6, opacity: 0.7 }}>{LAYER_LABELS[layer]}</span>
                    <span style={{
                      marginLeft: 8, padding: "1px 6px", borderRadius: 4, fontWeight: 700, fontFamily: "monospace",
                      background: count > 0 ? "var(--accent-subtle)" : "var(--bg-card-subtle)",
                    }}>{count}</span>
                  </div>
                );
              })}
            </div>

            {/* Findings */}
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {filteredFindings.length === 0 ? (
                <div style={{ textAlign: "center", padding: 48, color: "var(--text-muted)", fontSize: 14 }}>
                  {results.total_findings === 0 ? "🎉 Belge uyum kontrolünden geçti." : "Bu filtrede bulgu yok."}
                </div>
              ) : filteredFindings.map((f, i) => <FindingCard key={f.id} finding={f} index={i} />)}
            </div>
          </div>
        ) : (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: 300, color: "var(--text-muted)" }}>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: 48, marginBottom: 16, opacity: 0.25 }}>📋</div>
              <div style={{ fontSize: 15, color: "var(--text-secondary)" }}>Henüz dosya yüklenmedi</div>
              <div style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 4 }}>Sol taraftan bir belge yükleyerek başlayın</div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
