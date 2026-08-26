import { useRef, useState } from "react";
import { adminClient, type Question } from "../../api/adminClient";
import { Plus, Trash2, Pencil, RefreshCw, Sparkles, Loader2, X, Check, CheckCircle2, Circle } from "lucide-react";
import { Card, CardContent } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { Badge } from "../../components/ui/Badge";
import { useTranslation } from "react-i18next";

interface QuestionEditorProps {
  sectionId: string;
  // 9G: drives which type-specific fields render (CodingConfig/MCQConfig,
  // backend schemas/admin.py) — VERBAL stays plain title/competency/text.
  sectionType: string;
  questions: Question[];
  onRefresh: () => Promise<void>;
  status: string;
}

interface McqOptionDraft {
  id: string;
  text: string;
}

interface QuestionFormState {
  title: string;
  competency: string;
  text: string;
  // CODING (CodingConfig)
  starterCode: string;
  supportedLanguages: string; // comma-separated, parsed on submit
  constraints: string;
  hints: string; // one per line, parsed on submit
  // MCQ (MCQConfig)
  options: McqOptionDraft[];
  correctIds: string[];
  isMultiSelect: boolean;
}

const EMPTY_FORM: QuestionFormState = {
  title: "",
  competency: "",
  text: "",
  starterCode: "",
  supportedLanguages: "",
  constraints: "",
  hints: "",
  options: [],
  correctIds: [],
  isMultiSelect: false,
};

/** Parses an existing question's stored config (real CodingConfig/MCQConfig
 *  shape) back into the flat form-state fields above, for editing. */
function formFromQuestion(q: Question): QuestionFormState {
  const config = q.config || {};
  return {
    title: q.title,
    competency: q.competency || "",
    text: q.text,
    starterCode: config.starter_code || "",
    supportedLanguages: Array.isArray(config.supported_languages) ? config.supported_languages.join(", ") : "",
    constraints: config.constraints || "",
    hints: Array.isArray(config.hints) ? config.hints.join("\n") : "",
    options: Array.isArray(config.options) ? config.options.map((o: any) => ({ id: o.id, text: o.text })) : [],
    correctIds: Array.isArray(config.correct_answers) ? config.correct_answers : [],
    isMultiSelect: Boolean(config.is_multi_select),
  };
}

/** Builds the config payload (real CodingConfig/MCQConfig shape) to send to
 *  the backend, or undefined for VERBAL (which must not carry a config). */
function buildConfig(sectionType: string, form: QuestionFormState): any {
  if (sectionType === "CODING") {
    return {
      starter_code: form.starterCode,
      supported_languages: form.supportedLanguages.split(",").map((s) => s.trim()).filter(Boolean),
      constraints: form.constraints,
      hints: form.hints.split("\n").map((s) => s.trim()).filter(Boolean),
    };
  }
  if (sectionType === "MCQ") {
    return {
      options: form.options.map((o) => ({ id: o.id, text: o.text })),
      correct_answers: form.correctIds,
      is_multi_select: form.isMultiSelect,
    };
  }
  return undefined;
}

function isConfigComplete(sectionType: string, form: QuestionFormState): boolean {
  if (sectionType === "CODING") {
    return Boolean(
      form.starterCode.trim() &&
      form.supportedLanguages.split(",").map((s) => s.trim()).filter(Boolean).length > 0 &&
      form.constraints.trim()
    );
  }
  if (sectionType === "MCQ") {
    const filledOptions = form.options.filter((o) => o.text.trim());
    return filledOptions.length >= 2 && form.correctIds.length > 0;
  }
  return true;
}

export default function QuestionEditor({ sectionId, sectionType, questions, onRefresh, status }: QuestionEditorProps) {
  const { t } = useTranslation();
  const [loadingAction, setLoadingAction] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [numToGenerate, setNumToGenerate] = useState(5);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<QuestionFormState>(EMPTY_FORM);
  const [isAddingManual, setIsAddingManual] = useState(false);
  const [addForm, setAddForm] = useState<QuestionFormState>(EMPTY_FORM);
  const nextOptionId = useRef(1);

  const isDraft = status === "DRAFT";
  const sorted = [...questions].sort((a, b) => a.order_index - b.order_index);
  const textLabel = sectionType === "CODING"
    ? t('questionEditor.problemStatement')
    : sectionType === "MCQ"
    ? t('questionEditor.questionStem')
    : t('questionEditor.questionText');

  const handleGenerate = async () => {
    setLoadingAction("generate");
    setError("");
    try {
      await adminClient.generateQuestions(sectionId, numToGenerate);
      await onRefresh();
    } catch (err: any) {
      setError(err.message || t('questionEditor.failedToGenerate'));
    } finally {
      setLoadingAction(null);
    }
  };

  const startEdit = (q: Question) => {
    setEditingId(q.id);
    setEditForm(formFromQuestion(q));
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditForm(EMPTY_FORM);
  };

  const handleSaveEdit = async (questionId: string) => {
    setLoadingAction(`edit-${questionId}`);
    setError("");
    try {
      await adminClient.updateQuestion(questionId, {
        title: editForm.title,
        competency: editForm.competency || undefined,
        text: editForm.text,
        config: buildConfig(sectionType, editForm),
      });
      await onRefresh();
      cancelEdit();
    } catch (err: any) {
      setError(err.message || t('questionEditor.failedToUpdate'));
    } finally {
      setLoadingAction(null);
    }
  };

  const handleDelete = async (questionId: string) => {
    if (!confirm(t('questionEditor.deleteConfirm'))) return;
    setLoadingAction(`delete-${questionId}`);
    setError("");
    try {
      await adminClient.deleteQuestion(questionId);
      await onRefresh();
    } catch (err: any) {
      setError(err.message || t('questionEditor.failedToDelete'));
    } finally {
      setLoadingAction(null);
    }
  };

  const handleRegenerate = async (questionId: string) => {
    setLoadingAction(`regenerate-${questionId}`);
    setError("");
    try {
      await adminClient.regenerateQuestion(questionId);
      await onRefresh();
    } catch (err: any) {
      setError(err.message || t('questionEditor.failedToRegenerate'));
    } finally {
      setLoadingAction(null);
    }
  };

  const openAddManual = () => {
    setAddForm(sectionType === "MCQ"
      ? { ...EMPTY_FORM, options: [{ id: `opt-${nextOptionId.current++}`, text: "" }, { id: `opt-${nextOptionId.current++}`, text: "" }] }
      : EMPTY_FORM);
    setIsAddingManual(true);
  };

  const handleAddManual = async () => {
    if (!addForm.title.trim() || !addForm.text.trim()) return;
    if (!isConfigComplete(sectionType, addForm)) return;
    setLoadingAction("add-manual");
    setError("");
    try {
      await adminClient.createQuestion(sectionId, {
        title: addForm.title,
        competency: addForm.competency || undefined,
        text: addForm.text,
        config: buildConfig(sectionType, addForm),
      });
      await onRefresh();
      setIsAddingManual(false);
      setAddForm(EMPTY_FORM);
    } catch (err: any) {
      setError(err.message || t('questionEditor.failedToAdd'));
    } finally {
      setLoadingAction(null);
    }
  };

  const addOption = (form: QuestionFormState, setForm: (f: QuestionFormState) => void) => {
    setForm({ ...form, options: [...form.options, { id: `opt-${nextOptionId.current++}`, text: "" }] });
  };

  const removeOption = (form: QuestionFormState, setForm: (f: QuestionFormState) => void, id: string) => {
    setForm({
      ...form,
      options: form.options.filter((o) => o.id !== id),
      correctIds: form.correctIds.filter((cid) => cid !== id),
    });
  };

  const updateOptionText = (form: QuestionFormState, setForm: (f: QuestionFormState) => void, id: string, text: string) => {
    setForm({ ...form, options: form.options.map((o) => (o.id === id ? { ...o, text } : o)) });
  };

  const toggleCorrect = (form: QuestionFormState, setForm: (f: QuestionFormState) => void, id: string) => {
    if (form.isMultiSelect) {
      const has = form.correctIds.includes(id);
      setForm({ ...form, correctIds: has ? form.correctIds.filter((cid) => cid !== id) : [...form.correctIds, id] });
    } else {
      setForm({ ...form, correctIds: [id] });
    }
  };

  const setMultiSelect = (form: QuestionFormState, setForm: (f: QuestionFormState) => void, isMulti: boolean) => {
    // Switching single -> keep at most the first previously-marked option,
    // so `correct_answers` stays consistent with `is_multi_select` instead
    // of silently carrying stale extra selections.
    setForm({ ...form, isMultiSelect: isMulti, correctIds: isMulti ? form.correctIds : form.correctIds.slice(0, 1) });
  };

  const renderTypeFields = (form: QuestionFormState, setForm: (f: QuestionFormState) => void) => {
    if (sectionType === "CODING") {
      return (
        <div className="space-y-2 rounded-md border border-border bg-muted/20 p-3">
          <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">{t('questionEditor.starterCode')}</label>
          <textarea
            placeholder={t('questionEditor.starterCodePlaceholder')}
            value={form.starterCode}
            onChange={(e) => setForm({ ...form, starterCode: e.target.value })}
            className="w-full bg-background border border-input rounded-md px-2 py-1.5 text-sm font-mono"
            rows={4}
          />
          <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">{t('questionEditor.supportedLanguages')}</label>
          <input
            type="text"
            placeholder={t('questionEditor.supportedLanguagesPlaceholder')}
            value={form.supportedLanguages}
            onChange={(e) => setForm({ ...form, supportedLanguages: e.target.value })}
            className="w-full bg-background border border-input rounded-md px-2 py-1.5 text-sm"
          />
          <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">{t('questionEditor.constraints')}</label>
          <textarea
            placeholder={t('questionEditor.constraintsPlaceholder')}
            value={form.constraints}
            onChange={(e) => setForm({ ...form, constraints: e.target.value })}
            className="w-full bg-background border border-input rounded-md px-2 py-1.5 text-sm"
            rows={2}
          />
          <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">{t('questionEditor.hints')}</label>
          <textarea
            placeholder={t('questionEditor.hintsPlaceholder')}
            value={form.hints}
            onChange={(e) => setForm({ ...form, hints: e.target.value })}
            className="w-full bg-background border border-input rounded-md px-2 py-1.5 text-sm"
            rows={2}
          />
        </div>
      );
    }
    if (sectionType === "MCQ") {
      return (
        <div className="space-y-2 rounded-md border border-border bg-muted/20 p-3">
          <label className="flex items-center gap-2 text-xs font-medium text-foreground">
            <input
              type="checkbox"
              checked={form.isMultiSelect}
              onChange={(e) => setMultiSelect(form, setForm, e.target.checked)}
            />
            {t('questionEditor.allowMultipleCorrect')}
          </label>
          <div className="space-y-1.5">
            {form.options.map((option) => (
              <div key={option.id} className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => toggleCorrect(form, setForm, option.id)}
                  title={t('questionEditor.markCorrect')}
                  className={form.correctIds.includes(option.id) ? "text-green-600 shrink-0" : "text-muted-foreground shrink-0"}
                >
                  {form.correctIds.includes(option.id) ? <CheckCircle2 className="h-4 w-4" /> : <Circle className="h-4 w-4" />}
                </button>
                <input
                  type="text"
                  placeholder={t('questionEditor.optionPlaceholder')}
                  value={option.text}
                  onChange={(e) => updateOptionText(form, setForm, option.id, e.target.value)}
                  className="flex-1 bg-background border border-input rounded-md px-2 py-1.5 text-sm"
                />
                <button
                  type="button"
                  onClick={() => removeOption(form, setForm, option.id)}
                  disabled={form.options.length <= 2}
                  className="p-1 text-muted-foreground hover:text-destructive disabled:opacity-30 shrink-0"
                  title={t('questionEditor.removeOption')}
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
          <Button variant="outline" onClick={() => addOption(form, setForm)} className="h-7 px-2.5 text-xs inline-flex items-center gap-1">
            <Plus className="h-3.5 w-3.5" />
            {t('questionEditor.addOption')}
          </Button>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="mt-4 ps-4 border-s-2 border-border space-y-3">
      {error && (
        <div className="bg-red-500/10 border border-red-500/20 text-red-500 p-2 rounded-md text-xs">
          {error}
        </div>
      )}

      {isDraft && (
        <div className="flex items-center flex-wrap gap-2">
          <input
            type="number"
            min={1}
            max={20}
            value={numToGenerate}
            onChange={(e) => setNumToGenerate(Number(e.target.value))}
            className="w-16 bg-background border border-input rounded-md px-2 py-1.5 text-sm"
          />
          <Button
            variant="secondary"
            onClick={handleGenerate}
            disabled={loadingAction !== null}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 h-8 text-xs"
          >
            {loadingAction === "generate" ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Sparkles className="h-3.5 w-3.5" />
            )}
            <span>{t('questionEditor.generateQuestions')}</span>
          </Button>
          <Button
            variant="outline"
            onClick={openAddManual}
            disabled={loadingAction !== null || isAddingManual}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 h-8 text-xs"
          >
            <Plus className="h-3.5 w-3.5" />
            <span>{t('questionEditor.addManually')}</span>
          </Button>
        </div>
      )}

      {isAddingManual && (
        <Card>
          <CardContent className="p-3 space-y-2">
            <input
              type="text"
              placeholder={t('questionEditor.title')}
              value={addForm.title}
              onChange={(e) => setAddForm({ ...addForm, title: e.target.value })}
              className="w-full bg-background border border-input rounded-md px-2 py-1.5 text-sm"
            />
            <input
              type="text"
              placeholder={t('questionEditor.competencyOpt')}
              value={addForm.competency}
              onChange={(e) => setAddForm({ ...addForm, competency: e.target.value })}
              className="w-full bg-background border border-input rounded-md px-2 py-1.5 text-sm"
            />
            <textarea
              placeholder={textLabel}
              value={addForm.text}
              onChange={(e) => setAddForm({ ...addForm, text: e.target.value })}
              className="w-full bg-background border border-input rounded-md px-2 py-1.5 text-sm"
              rows={2}
            />
            {renderTypeFields(addForm, setAddForm)}
            <div className="flex items-center gap-2 pt-1">
              <Button
                onClick={handleAddManual}
                disabled={loadingAction === "add-manual" || !isConfigComplete(sectionType, addForm)}
                className="h-7 px-3 text-xs flex items-center gap-1.5"
              >
                {loadingAction === "add-manual" && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                <span>{t('questionEditor.add')}</span>
              </Button>
              <Button
                variant="ghost"
                onClick={() => { setIsAddingManual(false); setAddForm(EMPTY_FORM); }}
                disabled={loadingAction === "add-manual"}
                className="h-7 px-3 text-xs"
              >
                {t('questionEditor.cancel')}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {sorted.length === 0 ? (
        <p className="text-xs text-muted-foreground py-2">{t('questionEditor.noQuestions')}</p>
      ) : (
        <div className="space-y-2">
          {sorted.map((q) => (
            <Card key={q.id}>
              <CardContent className="p-3">
                {editingId === q.id ? (
                  <div className="space-y-2">
                    <input
                      type="text"
                      value={editForm.title}
                      onChange={(e) => setEditForm({ ...editForm, title: e.target.value })}
                      className="w-full bg-background border border-input rounded-md px-2 py-1.5 text-sm"
                    />
                    <input
                      type="text"
                      value={editForm.competency}
                      onChange={(e) => setEditForm({ ...editForm, competency: e.target.value })}
                      className="w-full bg-background border border-input rounded-md px-2 py-1.5 text-sm"
                      placeholder={t('questionEditor.competencyOpt')}
                    />
                    <textarea
                      value={editForm.text}
                      onChange={(e) => setEditForm({ ...editForm, text: e.target.value })}
                      className="w-full bg-background border border-input rounded-md px-2 py-1.5 text-sm"
                      rows={2}
                      placeholder={textLabel}
                    />
                    {renderTypeFields(editForm, setEditForm)}
                    <div className="flex items-center gap-2 pt-1">
                      <Button
                        onClick={() => handleSaveEdit(q.id)}
                        disabled={loadingAction === `edit-${q.id}` || !isConfigComplete(sectionType, editForm)}
                        className="h-7 px-3 text-xs flex items-center gap-1"
                      >
                        {loadingAction === `edit-${q.id}` ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Check className="h-3.5 w-3.5" />
                        )}
                        <span>{t('questionEditor.save')}</span>
                      </Button>
                      <Button
                        variant="ghost"
                        onClick={cancelEdit}
                        disabled={loadingAction === `edit-${q.id}`}
                        className="h-7 px-3 text-xs flex items-center gap-1"
                      >
                        <X className="h-3.5 w-3.5" />
                        <span>{t('questionEditor.cancel')}</span>
                      </Button>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-start justify-between">
                    <div className="space-y-1 min-w-0">
                      <h4 className="text-sm font-medium text-foreground">{q.title}</h4>
                      {q.competency && (
                        <Badge variant="secondary" className="text-[10px] uppercase">
                          {q.competency}
                        </Badge>
                      )}
                      <p className="text-xs text-muted-foreground">{q.text}</p>

                      {sectionType === "CODING" && q.config && (
                        <div className="flex flex-wrap items-center gap-1.5 pt-1">
                          {(q.config.supported_languages || []).map((lang: string) => (
                            <Badge key={lang} variant="outline" className="text-[10px]">{lang}</Badge>
                          ))}
                          {q.config.starter_code && (
                            <span className="text-[10px] text-muted-foreground">{t('questionEditor.hasStarterCode')}</span>
                          )}
                        </div>
                      )}

                      {sectionType === "MCQ" && q.config && (
                        <ul className="pt-1 space-y-0.5">
                          {(q.config.options || []).map((option: { id: string; text: string }) => (
                            <li key={option.id} className="flex items-center gap-1.5 text-xs">
                              {(q.config.correct_answers || []).includes(option.id) ? (
                                <CheckCircle2 className="h-3 w-3 text-green-600 shrink-0" />
                              ) : (
                                <Circle className="h-3 w-3 text-muted-foreground/50 shrink-0" />
                              )}
                              <span className={(q.config.correct_answers || []).includes(option.id) ? "text-foreground font-medium" : "text-muted-foreground"}>
                                {option.text}
                              </span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  {isDraft && (
                    <div className="flex items-center gap-1 shrink-0 ms-2">
                      <button
                        onClick={() => startEdit(q)}
                        disabled={loadingAction !== null}
                        className="p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground rounded-md disabled:opacity-30"
                        title={t('questionEditor.edit')}
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </button>
                      <button
                        onClick={() => handleRegenerate(q.id)}
                        disabled={loadingAction !== null}
                        className="p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground rounded-md disabled:opacity-30"
                        title={t('questionEditor.regenerate')}
                      >
                        {loadingAction === `regenerate-${q.id}` ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <RefreshCw className="h-3.5 w-3.5" />
                        )}
                      </button>
                      <button
                        onClick={() => handleDelete(q.id)}
                        disabled={loadingAction !== null}
                        className="p-1.5 text-red-500 hover:bg-red-500/10 rounded-md disabled:opacity-30"
                        title={t('questionEditor.delete')}
                      >
                        {loadingAction === `delete-${q.id}` ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Trash2 className="h-3.5 w-3.5" />
                        )}
                      </button>
                    </div>
                  )}
                </div>
              )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
