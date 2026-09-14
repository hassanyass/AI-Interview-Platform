import { useState } from "react";
import { Users, Globe, Check, Loader2, X } from "lucide-react";
import { Button } from "../../components/ui/Button";
import { useTranslation } from "react-i18next";

interface PublishSetupModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: (isPublic: boolean) => Promise<void>;
}

export default function PublishSetupModal({ isOpen, onClose, onConfirm }: PublishSetupModalProps) {
  const { t } = useTranslation();
  const [isPublic, setIsPublic] = useState(false);
  const [isPublishing, setIsPublishing] = useState(false);

  if (!isOpen) return null;

  const handleConfirm = async () => {
    setIsPublishing(true);
    try {
      await onConfirm(isPublic);
    } finally {
      setIsPublishing(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 animate-in fade-in duration-200">
      <div className="bg-background rounded-2xl shadow-xl w-full max-w-lg overflow-hidden border border-border flex flex-col animate-in zoom-in-95 duration-200">
        
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border/50">
          <h2 className="text-xl font-bold tracking-tight text-foreground">{t('publishSetup.title')}</h2>
          <button onClick={onClose} disabled={isPublishing} className="p-2 text-muted-foreground hover:bg-muted rounded-full transition-colors">
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          <div>
            <p className="text-sm text-muted-foreground font-medium mb-4 uppercase tracking-wider">{t('publishSetup.question')}</p>
            
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {/* Invitation Only Mode */}
              <div 
                onClick={() => setIsPublic(false)}
                className={`
                  cursor-pointer rounded-xl p-5 border-2 transition-all duration-200 relative
                  ${!isPublic 
                    ? "border-primary bg-primary/[0.03] shadow-sm" 
                    : "border-transparent bg-muted/40 hover:bg-muted/80 hover:border-border"}
                `}
              >
                <div className="flex items-center gap-3 mb-3">
                  <div className={`
                    flex h-10 w-10 shrink-0 items-center justify-center rounded-full transition-colors
                    ${!isPublic ? "bg-primary text-white shadow-md" : "bg-white text-muted-foreground shadow-sm"}
                  `}>
                    <Users className="h-5 w-5" />
                  </div>
                  <div className={`font-bold text-base leading-tight ${!isPublic ? "text-primary" : "text-foreground"}`}>
                    {t('publishSetup.invitationOnly')}
                  </div>
                </div>
                <p className={`text-sm leading-relaxed ${!isPublic ? "text-foreground/90" : "text-muted-foreground"}`}>
                  {t('publishSetup.invitationOnlyDesc')}
                </p>
                
                {/* Selection Indicator */}
                {!isPublic && (
                  <div className="absolute top-4 right-4 h-5 w-5 rounded-full bg-primary flex items-center justify-center text-white shadow-sm">
                    <Check className="h-3 w-3 stroke-[3]" />
                  </div>
                )}
              </div>

              {/* Public Access Mode */}
              <div 
                onClick={() => setIsPublic(true)}
                className={`
                  cursor-pointer rounded-xl p-5 border-2 transition-all duration-200 relative
                  ${isPublic 
                    ? "border-primary bg-primary/[0.03] shadow-sm" 
                    : "border-transparent bg-muted/40 hover:bg-muted/80 hover:border-border"}
                `}
              >
                <div className="flex items-center gap-3 mb-3">
                  <div className={`
                    flex h-10 w-10 shrink-0 items-center justify-center rounded-full transition-colors
                    ${isPublic ? "bg-primary text-white shadow-md" : "bg-white text-muted-foreground shadow-sm"}
                  `}>
                    <Globe className="h-5 w-5" />
                  </div>
                  <div className={`font-bold text-base leading-tight ${isPublic ? "text-primary" : "text-foreground"}`}>
                    {t('publishSetup.publicLink')}
                  </div>
                </div>
                <p className={`text-sm leading-relaxed ${isPublic ? "text-foreground/90" : "text-muted-foreground"}`}>
                  {t('publishSetup.publicLinkDesc')}
                </p>
                
                {/* Selection Indicator */}
                {isPublic && (
                  <div className="absolute top-4 right-4 h-5 w-5 rounded-full bg-primary flex items-center justify-center text-white shadow-sm">
                    <Check className="h-3 w-3 stroke-[3]" />
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-border/50 bg-muted/10 flex justify-end gap-3">
          <Button variant="outline" onClick={onClose} disabled={isPublishing}>{t('publishSetup.cancel')}</Button>
          <Button onClick={handleConfirm} disabled={isPublishing} className="min-w-[140px]">
            {isPublishing ? <Loader2 className="h-4 w-4 animate-spin" /> : t('publishSetup.confirm')}
          </Button>
        </div>
      </div>
    </div>
  );
}
