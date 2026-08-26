import re

with open('temp.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace specific background and text colors to match Himma brand
replacements = {
    'bg-[#f6f8fb]': 'bg-background',
    'bg-slate-950': 'bg-secondary',
    'text-slate-950': 'text-foreground',
    'text-white': 'text-secondary-foreground',
    'bg-white': 'bg-card',
    'border-slate-200': 'border-border',
    'text-slate-500': 'text-muted-foreground',
    'bg-slate-100': 'bg-muted',
    'bg-sky-500': 'bg-primary',
    'text-sky-900': 'text-primary',
    'bg-sky-50': 'bg-primary/10',
    'text-sky-600': 'text-primary',
    'text-sky-700': 'text-primary',
    'border-sky-200': 'border-primary/20',
    'bg-sky-100': 'bg-primary/20',
    'bg-emerald-500': 'bg-success',
    'bg-emerald-50': 'bg-success/10',
    'text-emerald-900': 'text-success',
    'text-emerald-600': 'text-success',
    'border-emerald-200': 'border-success/20',
    'bg-emerald-100': 'bg-success/20',
    'text-emerald-500': 'text-success',
    'shadow-[0_2px_8px_rgba(15,23,42,0.04)]': 'shadow-sm',
    'bg-[#20252b]': 'bg-secondary',
    'border-slate-800': 'border-secondary',
    'text-sky-300': 'text-primary/70',
    'hover:bg-sky-400': 'hover:bg-primary/90',
}

for old, new in replacements.items():
    content = content.replace(old, new)

# Custom replace for the header logo
content = re.sub(
    r'<div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-secondary text-sm font-semibold text-secondary-foreground shadow-sm">P</div>',
    r'<div className="flex items-center gap-2 font-bold text-xl tracking-tight text-primary">e& <span className="text-muted-foreground font-normal">|</span> هِمّة</div>',
    content
)

# Fix the report loading background
content = content.replace('bg-slate-50 min-h-[300px]', 'bg-background min-h-[300px]')

with open('C:\\Users\\hassa\\Documents\\AI-Interview-Platform\\frontend\\src\\features\\interview-session\\InterviewWorkspace.tsx', 'w', encoding='utf-8') as f:
    f.write(content)
