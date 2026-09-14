import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { adminClient } from "../../api/adminClient";
import { ArrowLeft } from "lucide-react";
import { Link } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { useTranslation } from "react-i18next";

export default function JobCreatePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");

  const [formData, setFormData] = useState({
    title: "",
    description: "",
    seniority: "",
    location: "",
    language: "en",
    instructions: "", // Real API field name
    required_skills: "",
    preferred_skills: "",
    responsibilities: "",
    duration_minutes: "15",
  });

  const parseArrayText = (text: string): string[] => {
    if (!text) return [];
    return text
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line.length > 0);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setError("");

    try {
      // 1. Create Job (Atomically creates the definition on the backend)
      const job = await adminClient.createJob({
        title: formData.title,
        description: formData.description || undefined,
        seniority: formData.seniority || undefined,
        location: formData.location || undefined,
        language: formData.language,
        instructions: formData.instructions || undefined,
        required_skills: parseArrayText(formData.required_skills).length ? parseArrayText(formData.required_skills) : undefined,
        preferred_skills: parseArrayText(formData.preferred_skills).length ? parseArrayText(formData.preferred_skills) : undefined,
        responsibilities: parseArrayText(formData.responsibilities).length ? parseArrayText(formData.responsibilities) : undefined,
      });

      // 2. Patch InterviewDefinition for duration
      if (job.definition) {
        try {
          await adminClient.updateDefinition(job.definition.id, {
            duration_minutes: parseInt(formData.duration_minutes, 10),
          });
        } catch (patchErr) {
          console.error("Failed to set duration:", patchErr);
          // We redirect on partial failure per user request so the user sees the real state
          alert("Job created, but setting duration failed. Please update it on the job page.");
        }
      }

      // Success or partial success -> navigate to job detail
      navigate(`/admin/jobs/${job.id}`);
    } catch (err: any) {
      setError(err.message || t('jobCreate.failed'));
      setIsSubmitting(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-6 pb-12">
      <div className="flex items-center gap-4">
        <Link to="/admin/jobs">
          <Button variant="outline" className="p-2 h-10 w-10">
            <ArrowLeft className="h-5 w-5" />
          </Button>
        </Link>
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{t('jobCreate.title')}</h1>
          <p className="text-muted-foreground mt-1">{t('jobCreate.desc')}</p>
        </div>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 text-red-500 p-4 rounded-md">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-xl">{t('jobCreate.basicInfo')}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4">
              <div>
              <label className="block text-sm font-medium mb-1">{t('jobCreate.jobTitle')}</label>
              <input
                required
                type="text"
                value={formData.title}
                onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                className="w-full bg-background border border-input rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary/50"
                placeholder={t('jobCreate.jobTitlePlaceholder')}
              />
            </div>

            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium mb-1">{t('jobCreate.seniority')}</label>
                <input
                  type="text"
                  value={formData.seniority}
                  onChange={(e) => setFormData({ ...formData, seniority: e.target.value })}
                  className="w-full bg-background border border-input rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary/50"
                  placeholder={t('jobCreate.seniorityPlaceholder')}
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">{t('jobCreate.location')}</label>
                <input
                  type="text"
                  value={formData.location}
                  onChange={(e) => setFormData({ ...formData, location: e.target.value })}
                  className="w-full bg-background border border-input rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary/50"
                  placeholder={t('jobCreate.locationPlaceholder')}
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">{t('jobCreate.language')}</label>
                <select
                  required
                  value={formData.language}
                  onChange={(e) => setFormData({ ...formData, language: e.target.value })}
                  className="w-full bg-background border border-input rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary/50"
                >
                  <option value="en">{t('jobCreate.english')}</option>
                  <option value="ar">{t('jobCreate.arabic')}</option>
                </select>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">{t('jobCreate.jobDesc')}</label>
              <textarea
                rows={4}
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                className="w-full bg-background border border-input rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary/50 resize-y"
                placeholder={t('jobCreate.jobDescPlaceholder')}
              />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-xl">{t('jobCreate.aiGen')}</CardTitle>
            <CardDescription>{t('jobCreate.aiGenDesc')}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4">
              <div>
              <label className="block text-sm font-medium mb-1">{t('jobCreate.reqSkills')}</label>
              <p className="text-xs text-muted-foreground mb-2">{t('jobCreate.reqSkillsDesc')}</p>
              <textarea
                rows={3}
                value={formData.required_skills}
                onChange={(e) => setFormData({ ...formData, required_skills: e.target.value })}
                className="w-full bg-background border border-input rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary/50 resize-y"
                placeholder={t('jobCreate.reqSkillsPlaceholder')}
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">{t('jobCreate.prefSkills')}</label>
              <p className="text-xs text-muted-foreground mb-2">{t('jobCreate.prefSkillsDesc')}</p>
              <textarea
                rows={3}
                value={formData.preferred_skills}
                onChange={(e) => setFormData({ ...formData, preferred_skills: e.target.value })}
                className="w-full bg-background border border-input rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary/50 resize-y"
                placeholder={t('jobCreate.prefSkillsPlaceholder')}
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">{t('jobCreate.resp')}</label>
              <p className="text-xs text-muted-foreground mb-2">{t('jobCreate.respDesc')}</p>
              <textarea
                rows={3}
                value={formData.responsibilities}
                onChange={(e) => setFormData({ ...formData, responsibilities: e.target.value })}
                className="w-full bg-background border border-input rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary/50 resize-y"
                placeholder={t('jobCreate.respPlaceholder')}
              />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-xl">{t('jobCreate.candExp')}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4">
              <div>
              <label className="block text-sm font-medium mb-1">{t('jobCreate.candInst')}</label>
              <textarea
                rows={2}
                value={formData.instructions}
                onChange={(e) => setFormData({ ...formData, instructions: e.target.value })}
                className="w-full bg-background border border-input rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary/50 resize-y"
                placeholder={t('jobCreate.candInstPlaceholder')}
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">{t('jobCreate.duration')}</label>
              <input
                required
                type="number"
                min="5"
                max="120"
                value={formData.duration_minutes}
                onChange={(e) => setFormData({ ...formData, duration_minutes: e.target.value })}
                className="w-48 bg-background border border-input rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary/50"
              />
              </div>
            </div>
          </CardContent>
        </Card>

        <div className="flex justify-end gap-4 pt-2">
          <Link to="/admin/jobs">
            <Button type="button" variant="outline" className="px-6">{t('jobCreate.cancel')}</Button>
          </Link>
          <Button
            type="submit"
            disabled={isSubmitting}
            className="px-8"
          >
            {isSubmitting ? t('jobCreate.creating') : t('jobCreate.createJob')}
          </Button>
        </div>
      </form>
    </div>
  );
}
