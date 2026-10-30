import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  BrainCircuit,
  Sparkles,
  BookOpen,
  GraduationCap,
  Send,
  Loader2,
  CheckCircle2,
  AlertCircle,
  RotateCcw,
  Zap,
  FileUp,
  FileText,
  Trash2,
  Search,
  BarChart3,
  History,
  ArrowUpRight,
} from "lucide-react";
import "./App.css";

const API = "http://127.0.0.1:8000";

function App() {
  const [activePage, setActivePage] = useState("coach");

  // Existing answer-evaluation feature
  const [subject, setSubject] = useState("Artificial Intelligence");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [marks, setMarks] = useState(10);
  const [evaluation, setEvaluation] = useState("");
  const [evaluationLoading, setEvaluationLoading] = useState(false);
  const [evaluationError, setEvaluationError] = useState("");

  // Past Paper Intelligence feature
  const [university, setUniversity] = useState("");
  const [paperSubject, setPaperSubject] = useState("");
  const [examType, setExamType] = useState("End-semester examination");
  const [paperFiles, setPaperFiles] = useState([]);
  const [paperResult, setPaperResult] = useState(null);
  const [paperLoading, setPaperLoading] = useState(false);
  const [paperError, setPaperError] = useState("");
  const [priorityFilter, setPriorityFilter] = useState("All");

  async function evaluateAnswer(event) {
    event.preventDefault();
    setEvaluationLoading(true);
    setEvaluationError("");
    setEvaluation("");

    try {
      const response = await fetch(`${API}/api/evaluate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: `[Subject: ${subject}] ${question}`,
          answer,
          max_marks: Number(marks),
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Evaluation failed.");
      setEvaluation(data.evaluation || "No evaluation was returned.");
    } catch (error) {
      setEvaluationError(error.message || "Could not connect to the RASEGAN backend.");
    } finally {
      setEvaluationLoading(false);
    }
  }

  function resetEvaluation() {
    setQuestion("");
    setAnswer("");
    setEvaluation("");
    setEvaluationError("");
  }

  function addPaperFiles(event) {
    const incoming = Array.from(event.target.files || []);
    const valid = incoming.filter((file) => file.name.toLowerCase().endsWith(".pdf"));
    setPaperFiles((current) => {
      const merged = [...current];
      for (const file of valid) {
        if (!merged.some((existing) => existing.name === file.name && existing.size === file.size)) {
          merged.push(file);
        }
      }
      return merged.slice(0, 10);
    });
    setPaperError(incoming.length !== valid.length ? "Only PDF files are supported." : "");
    event.target.value = "";
  }

  function removePaperFile(indexToRemove) {
    setPaperFiles((current) => current.filter((_, index) => index !== indexToRemove));
  }

  async function analyzePapers(event) {
    event.preventDefault();
    setPaperError("");
    setPaperResult(null);

    if (paperFiles.length === 0) {
      setPaperError("Upload at least one previous-year question paper in PDF format.");
      return;
    }
    if (!paperSubject.trim()) {
      setPaperError("Enter the subject before starting the analysis.");
      return;
    }

    const formData = new FormData();
    paperFiles.forEach((file) => formData.append("files", file));
    formData.append("university", university.trim() || "Not specified");
    formData.append("subject", paperSubject.trim());
    formData.append("exam_type", examType);

    setPaperLoading(true);
    try {
      const response = await fetch(`${API}/api/past-papers/analyze`, {
        method: "POST",
        body: formData,
      });
      const data = await response.json();
      if (!response.ok) {
        const detail = data.detail;
        let message = typeof detail === "string"
          ? detail
          : (detail?.message || "Past-paper analysis failed.");

        // The backend returns per-file reasons when no PDF can be analysed.
        // Surface those reasons in the UI instead of hiding them behind the 422 message.
        if (Array.isArray(detail?.file_errors) && detail.file_errors.length > 0) {
          const fileLines = detail.file_errors.map((item) =>
            `• ${item.file || "PDF"}: ${item.error || "Unknown file error"}`
          );
          message = `${message}\n\n${fileLines.join("\n")}`;
        } else if (typeof detail !== "string" && !detail?.message) {
          message = JSON.stringify(detail || data);
        }
        throw new Error(message);
      }
      setPaperResult(data);
    } catch (error) {
      setPaperError(error.message || "Could not analyse the uploaded papers.");
    } finally {
      setPaperLoading(false);
    }
  }

  const visibleRankedQuestions = useMemo(() => {
    const rows = paperResult?.ranked_questions || [];
    return priorityFilter === "All"
      ? rows
      : rows.filter((item) => item.priority === priorityFilter);
  }, [paperResult, priorityFilter]);

  function prepareQuestion(item) {
    setSubject(paperSubject || "Artificial Intelligence");
    setQuestion(item.representative_question || "");
    setMarks(item.average_marks ? Math.max(1, Math.round(item.average_marks)) : 10);
    setAnswer("");
    setEvaluation("");
    setEvaluationError("");
    setActivePage("coach");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  return (
    <div className="app">
      <nav className="navbar">
        <div className="brand">
          <div className="brand-icon"><BrainCircuit size={23} /></div>
          <span>RASEGAN<span className="brand-ai">.AI</span></span>
        </div>
        <div className="nav-center">
          <button className={`nav-link ${activePage === "coach" ? "nav-active" : ""}`} onClick={() => setActivePage("coach")}>
            Exam Coach
          </button>
          <button className={`nav-link ${activePage === "papers" ? "nav-active" : ""}`} onClick={() => setActivePage("papers")}>
            Past Paper Intelligence
          </button>
        </div>
        <div className="nav-status"><span className="status-dot" /> AI Engine <span className="model-tag">NEMOTRON</span></div>
      </nav>

      <main className="main">
        <section className="hero">
          <motion.div className="orb-wrap" animate={{ y: [0, -10, 0] }} transition={{ duration: 4, repeat: Infinity }}>
            <div className="orb"><div className="orb-core"><BrainCircuit size={43} /></div></div>
            <div className="orb-ring ring-one" /><div className="orb-ring ring-two" />
          </motion.div>
          <div className="eyebrow"><Sparkles size={14} /> YOUR PERSONAL AI EXAM COACH</div>
          <h1>Prepare smarter.<br /><span>Perform better.</span></h1>
          <p className="hero-text">Practice university questions, analyse previous-year papers and get intelligent feedback powered by NVIDIA Nemotron.</p>
        </section>

        {activePage === "coach" ? (
          <section className="workspace">
            <div className="workspace-heading">
              <div><div className="section-label">YOUR WORKSPACE</div><h2>Answer Evaluation</h2><p>Submit an answer and let AI evaluate your understanding.</p></div>
              <div className="powered"><Zap size={14} /> Powered by Nemotron</div>
            </div>
            <form onSubmit={evaluateAnswer}>
              <div className="field">
                <label><GraduationCap size={16} /> SUBJECT</label>
                <select value={subject} onChange={(event) => setSubject(event.target.value)}>
                  <option>Artificial Intelligence</option><option>Machine Learning</option><option>Data Structures</option><option>Mathematics</option><option>Computer Networks</option><option>Physics</option><option>Electrical Engineering</option><option>Other</option>
                </select>
              </div>
              <div className="field"><label><BookOpen size={16} /> EXAM QUESTION</label><textarea value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Paste your university exam question here..." required minLength={5} rows={4} /></div>
              <div className="field"><label><BrainCircuit size={16} /> YOUR ANSWER</label><textarea value={answer} onChange={(event) => setAnswer(event.target.value)} placeholder="Write your answer as you would in an actual examination..." required rows={7} /></div>
              <div className="bottom-controls">
                <div className="marks-control"><label>MAXIMUM MARKS</label><select value={marks} onChange={(event) => setMarks(event.target.value)}>{[5, 10, 15, 20, 25, 50, 100].map((number) => <option key={number} value={number}>{number} marks</option>)}</select></div>
                <button className="reset-btn" type="button" onClick={resetEvaluation}><RotateCcw size={16} /> Reset</button>
                <button className="submit-btn" type="submit" disabled={evaluationLoading}>{evaluationLoading ? <><Loader2 className="spin" size={17} /> Evaluating...</> : <><Send size={17} /> Evaluate my answer</>}</button>
              </div>
            </form>
            {evaluationError && <div className="error-box"><AlertCircle size={19} /> {evaluationError}</div>}
            {evaluationLoading && <div className="loading-box"><Loader2 className="spin" size={25} /><div><strong>Nemotron is evaluating your answer</strong><p>Checking accuracy, concepts and completeness...</p></div></div>}
            {evaluation && <motion.section className="result-box" initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }}><div className="result-heading"><CheckCircle2 size={21} /><div><h3>Evaluation complete</h3><p>Your AI-generated examination feedback</p></div></div><div className="result-content">{evaluation}</div></motion.section>}
          </section>
        ) : (
          <section className="workspace">
            <div className="workspace-heading">
              <div><div className="section-label">EXAM TREND ANALYSIS</div><h2>Past Paper Intelligence</h2><p>Upload previous-year papers. RASEGAN finds recurring question patterns and ranks what to prepare first.</p></div>
              <div className="powered"><Search size={14} /> Historical analysis</div>
            </div>

            <form onSubmit={analyzePapers}>
              <div className="paper-form-grid">
                <div className="field"><label><GraduationCap size={16} /> UNIVERSITY / INSTITUTION</label><input value={university} onChange={(event) => setUniversity(event.target.value)} placeholder="e.g. University name" /></div>
                <div className="field"><label><BookOpen size={16} /> SUBJECT</label><input value={paperSubject} onChange={(event) => setPaperSubject(event.target.value)} placeholder="e.g. Artificial Intelligence" required /></div>
                <div className="field"><label><History size={16} /> EXAM TYPE</label><select value={examType} onChange={(event) => setExamType(event.target.value)}><option>End-semester examination</option><option>Mid-semester examination</option><option>Annual examination</option><option>University entrance examination</option><option>Other</option></select></div>
              </div>

              <div className="upload-panel">
                <div className="upload-icon"><FileUp size={26} /></div>
                <h3>Upload previous-year question papers</h3>
                <p>Choose up to 10 text-based PDF papers, maximum 15 MB each. Include the year in each filename where possible, for example AI_2024.pdf.</p>
                <label className="upload-button"><FileUp size={16} /> Select PDF papers<input type="file" accept="application/pdf,.pdf" multiple onChange={addPaperFiles} /></label>
                <div className="upload-limits">PDF only · Up to 10 files · 15 MB per file · Text-based PDFs only (OCR not enabled)</div>
              </div>

              {paperFiles.length > 0 && <div className="file-list"><div className="file-list-heading">Selected papers ({paperFiles.length}/10)</div>{paperFiles.map((file, index) => <div className="file-row" key={`${file.name}-${file.size}-${index}`}><FileText size={18} /><div className="file-meta"><strong>{file.name}</strong><span>{(file.size / (1024 * 1024)).toFixed(2)} MB</span></div><button className="icon-button" type="button" aria-label={`Remove ${file.name}`} onClick={() => removePaperFile(index)}><Trash2 size={16} /></button></div>)}</div>}

              <div className="bottom-controls paper-submit-row"><div className="marks-control"><label>ANALYSIS METHOD</label><span className="method-label">Nemotron extraction + historical scoring</span></div><button className="submit-btn" type="submit" disabled={paperLoading || paperFiles.length === 0}>{paperLoading ? <><Loader2 className="spin" size={17} /> Analysing papers...</> : <><Search size={17} /> Analyse past papers</>}</button></div>
            </form>

            {paperError && <div className="error-box"><AlertCircle size={19} /> {paperError}</div>}
            {paperLoading && <div className="loading-box"><Loader2 className="spin" size={25} /><div><strong>Nemotron is analysing your papers</strong><p>Extracting questions, grouping similar concepts and calculating historical priority. This may take a little while.</p></div></div>}

            {paperResult && (
              <motion.section className="paper-results" initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }}>
                <div className="result-heading"><CheckCircle2 size={21} /><div><h3>Past-paper analysis complete</h3><p>Priority scores reflect the supplied papers—not guaranteed future exam probabilities.</p></div></div>
                <div className="stats-grid">
                  <div className="stat-card"><span>PAPERS ANALYSED</span><strong>{paperResult.metadata?.papers_analysed ?? 0}</strong></div>
                  <div className="stat-card"><span>QUESTIONS EXTRACTED</span><strong>{paperResult.metadata?.questions_extracted ?? 0}</strong></div>
                  <div className="stat-card"><span>QUESTION FAMILIES</span><strong>{paperResult.metadata?.question_families ?? 0}</strong></div>
                  <div className="stat-card"><span>YEARS COVERED</span><strong>{paperResult.metadata?.years_covered?.length ? paperResult.metadata.years_covered.join(", ") : "Not found"}</strong></div>
                </div>
                <div className="papers-analysed-list"><strong>Processed files</strong>{(paperResult.papers || []).map((paper) => <span key={paper.filename}><FileText size={14} /> {paper.filename} · {paper.questions_extracted} questions</span>)}</div>
                {Number(paperResult.metadata?.papers_analysed || 0) < 5 && <div className="sample-warning"><strong>Limited historical sample</strong><span>RASEGAN analysed {paperResult.metadata?.papers_analysed || 0} paper(s). Upload at least 5 papers from different exam years for more useful comparisons. Scores are discounted for small samples and are not exam probabilities.</span></div>}
                {paperResult.file_errors?.length > 0 && <div className="file-warning"><strong>Some files could not be analysed</strong>{paperResult.file_errors.map((item, index) => <p key={`${item.file}-${index}`}>{item.file}: {item.error}</p>)}</div>}
                <div className="ranked-heading"><div><div className="section-label">YOUR PREPARATION PRIORITIES</div><h3>Ranked important questions</h3></div><BarChart3 size={22} /></div>
                <div className="filter-row">{["All", "High", "Medium", "Low"].map((filter) => <button type="button" key={filter} className={`filter-chip ${priorityFilter === filter ? "selected" : ""}`} onClick={() => setPriorityFilter(filter)}>{filter} priority</button>)}</div>
                {visibleRankedQuestions.length === 0 ? <p className="empty-state">No questions match this filter.</p> : visibleRankedQuestions.map((item, index) => <article className="rank-card" key={`${item.label}-${index}`}>
                  <div className="rank-top"><span className="rank-number">#{index + 1}</span><span className={`priority-pill ${String(item.priority).toLowerCase()}`}>{item.priority} priority</span><span className="score-label">Priority score <strong>{item.priority_score}/100</strong></span></div>
                  <h4>{item.label}</h4>
                  <p className="representative-question">{item.representative_question}</p>
                  <div className="rank-metrics"><span><strong>{item.appearance_count}/{item.total_papers}</strong> papers</span><span><strong>{item.historical_frequency_percent}%</strong> historical frequency</span><span><strong>{item.years_appeared?.length ? item.years_appeared.join(", ") : "Year unknown"}</strong> years appeared</span><span><strong>{item.data_confidence || "Not reported"}</strong> data confidence</span>{item.average_marks != null && <span><strong>{item.average_marks}</strong> avg. marks</span>}</div>
                  <div className="priority-bar"><span style={{ width: `${Math.max(0, Math.min(100, item.priority_score || 0))}%` }} /></div>
                  <div className="rank-footer"><span>{[item.unit, item.topic].filter(Boolean).join(" · ") || "Topic not identified"}</span><button type="button" className="prepare-button" onClick={() => prepareQuestion(item)}>Prepare this question <ArrowUpRight size={15} /></button></div>
                  {item.question_variants?.length > 1 && <details className="variants"><summary>View {item.question_variants.length} source question versions</summary>{item.question_variants.map((variant, variantIndex) => <p key={`${variant.source_file}-${variantIndex}`}>“{variant.question}” <span>— {variant.source_file}{variant.marks ? ` · ${variant.marks} marks` : ""}</span></p>)}</details>}
                </article>)}
                <p className="disclaimer">Important: historical frequency is calculated from the successfully analysed papers. A high priority score means a topic deserves preparation attention; it is not a statistically validated probability of appearing in the next exam.</p>
              </motion.section>
            )}
          </section>
        )}

        <footer><span>RASEGAN AI © 2026</span><span>Built for university students worldwide</span><span>AI powered by NVIDIA Nemotron</span></footer>
      </main>
    </div>
  );
}

export default App;
