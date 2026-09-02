import { useEffect, useState } from "react";
import { useApi } from "../api";
import type { InvestigationResult } from "../api";
import { useParams } from "react-router-dom";

export const InvestigationPage = () => {
  const { caseId } = useParams<{ caseId: string }>();
  const api = useApi();

  const [investigationHistory, setInvestigationHistory] = useState<InvestigationResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    const loadInvestigationHistory = async () => {
      if (!caseId) {
        setError("No case ID provided");
        setLoading(false);
        return;
      }

      try {
        setError(null);
        const response = await api.getInvestigationHistory(caseId);
        setInvestigationHistory(response || []);
        setLoading(false);
      } catch (err: any) {
        setError(err.message || "Failed to load investigation history");
        console.error("Load investigation history error:", err);
        setLoading(false);
      }
    };

    loadInvestigationHistory();
  }, [caseId, api, retryCount]);

  if (error) {
    return (
      <div className="error-state">
        <h3>Error loading investigation history</h3>
        <p>{error}</p>
        <button onClick={() => setRetryCount(c => c + 1)}>Retry</button>
      </div>
    );
  }

  if (loading) {
    return <div>Loading investigation history...</div>;
  }

  const result = investigationHistory[investigationHistory.length - 1];

  return (
    <section className="investigation-history-section">
      <h2>Investigation History: {caseId}</h2>

      {investigationHistory.length === 0 && (
        <p>No investigations found for this case.</p>
      )}

      <ol className="investigation-list">
        {investigationHistory.map((inv, idx) => (
          <li key={idx} className="investigation-list-item">
            <div className="list-item-header">
              <span className="list-item-timestamp">
                {inv.started_at ? new Date(inv.started_at).toLocaleString() : "N/A"}
              </span>
              <span className="list-item-status status-{inv.status.toLowerCase()}">
                {inv.status}
              </span>
            </div>

            <div className="list-item-details">
              <p><strong>Investigation ID:</strong> {inv.investigation_id}</p>
              <p><strong>Model:</strong> {inv.model_name} {inv.model_available ? "(available)" : "(not available)"}</p>
              <p><strong>Recommendation:</strong> {inv.recommendation}</p>
              <p><strong>Confidence:</strong> {inv.confidence}%</p>
              <p><strong>Duration:</strong> {inv.duration_ms} ms</p>
              {typeof inv.tool_calls === "number" && inv.tool_calls > 0 && (
                <p><strong>Tool Calls:</strong> {String(inv.tool_calls)}</p>
              )}
              {inv.failure_reason && (
                <p className="failure-reason">
                  <strong>Failure Reason:</strong> {inv.failure_reason}
                </p>
              )}
            </div>
          </li>
        ))}
      </ol>

      {result && (
        <div className="latest-result-summary">
          <h3>Latest Result Summary</h3>
          <p><strong>Recommendation:</strong> {result.recommendation}</p>
          <p><strong>Confidence:</strong> {result.confidence}%</p>
          <p><strong>Findings:</strong> {result.findings?.join(", ") || "None"}.</p>
          <p><strong>Missing Evidence:</strong> {result.missing_evidence?.join(", ") || "None"}.</p>
        </div>
      )}
    </section>
  );
};