"""Generate the single-file LaTeX manuscript from the Markdown sources.

docs/paper/MANUSCRIPT.md is the source of truth; the related-work section is
pulled from docs/paper/RELATED_WORK.md where MANUSCRIPT.md says
<!-- include RELATED_WORK -->. Output: docs/paper/manuscript.tex, one file as
the Springer Nature template requires. Only the Markdown this manuscript uses
is supported: headings, paragraphs, pipe tables, flat lists, **bold**,
*italic*, `code`, citations written [Key] or [Key1, Key2], and ```latex fenced
blocks passed through verbatim. Unknown non-ASCII characters stop the build
rather than being silently mangled. Build with: python scripts/build_manuscript.py --pdf
"""
import re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];PAPER=ROOT/'docs/paper'

UNICODE={'−':'$-$','×':'$\\times$','±':'$\\pm$','≥':'$\\geq$','≤':'$\\leq$','λ':'$\\lambda$','÷':'$\\div$','·':'$\\cdot$',
 'Å':'\\AA{}','–':'--','—':'---','’':"'",'‘':'`','“':'``','”':"''",'…':'\\ldots{}','≈':'$\\approx$','→':'$\\rightarrow$',
 'Δ':'$\\Delta$','é':"\\'e",'ł':'\\l{}','ö':'\\"o','ü':'\\"u','í':"\\'i",'á':"\\'a",'µ':'$\\mu$','∼':'$\\sim$','²':'$^2$'}
ESC={'\\':'\\textbackslash{}','&':'\\&','%':'\\%','#':'\\#','_':'\\_','$':'\\$','~':'\\textasciitilde{}','^':'\\textasciicircum{}','{':'\\{','}':'\\}'}
CITE=re.compile(r'\[((?:[A-Za-z][A-Za-z0-9]*\d{2}|FriendlyCaptcha|Anubis|PlayIntegrity|RateLimitDraft|TorProp327|RFC\d{4})(?:,\s*(?:[A-Za-z][A-Za-z0-9]*\d{2}|FriendlyCaptcha|Anubis|PlayIntegrity|RateLimitDraft|TorProp327|RFC\d{4}))*)\]')

def text(s):
 """Escape a prose fragment, keeping citations, emphasis and code."""
 out=[];pos=0
 token=re.compile(r'(`[^`]+`)|(\*\*[^*]+\*\*)|(\*[^*\s][^*]*\*)|'+CITE.pattern+r'|(https?://[^\s)]+[^\s).,;])')
 for m in token.finditer(s):
  out.append(plain(s[pos:m.start()]));pos=m.end()
  if m.group(1):out.append('\\texttt{'+plain(m.group(1)[1:-1])+'}')
  elif m.group(2):out.append('\\textbf{'+text(m.group(2)[2:-2])+'}')
  elif m.group(3):out.append('\\emph{'+text(m.group(3)[1:-1])+'}')
  elif m.group(4):
   if out and out[-1].endswith(' '):out[-1]=out[-1][:-1]
   out.append('~\\citep{'+','.join(k.strip() for k in m.group(4).split(','))+'}')
  else:out.append('\\url{'+m.group(5)+'}')
 out.append(plain(s[pos:]));return ''.join(out)

def plain(s):
 r=[]
 for ch in s:
  if ch in ESC:r.append(ESC[ch])
  elif ord(ch)<128:r.append(ch)
  elif ch in UNICODE:r.append(UNICODE[ch])
  else:raise ValueError('Unmapped character %r in: %s'%(ch,s[:80]))
 return ''.join(r).replace('$$','')

def table(rows,caption):
 if not caption:raise ValueError('Every table needs a "Table: caption" line: '+rows[0][:60])
 cells=[[c.strip() for c in r.strip().strip('|').split('|')] for r in rows]
 head,body=cells[0],cells[2:];align=''.join('r' if a.strip().endswith(':') else 'X' for a in cells[1])
 lines=['\\begin{table}[htbp]','\\caption{'+text(caption)+'}','\\centering','\\small','\\begin{tabularx}{\\textwidth}{'+align+'}','\\toprule',' & '.join(text(c) for c in head)+' \\\\','\\midrule']
 lines+=[' & '.join(text(c) for c in r)+' \\\\' for r in body];lines+=['\\botrule','\\end{tabularx}','\\end{table}']
 return '\n'.join(lines)

def body(md,level_shift=0):
 out=[];lines=md.split('\n');i=0;para=[];caption=None
 def flush():
  if para:out.append(text(' '.join(para)));out.append('');para.clear()
 while i<len(lines):
  line=lines[i]
  if line.startswith('```latex'):
   flush();j=lines.index('```',i+1);out.append('\n'.join(lines[i+1:j]));out.append('');i=j+1;continue
  if line.startswith('<!--'):flush();i+=1;continue
  m=re.match(r'^(#{2,4}) (.*)',line)
  if m:
   flush();depth=len(m.group(1))-2+level_shift;title=re.sub(r'^\d+(\.\d+)* ','',m.group(2))
   out.append(['\\section','\\subsection','\\subsubsection','\\paragraph'][depth]+'{'+text(title)+'}');out.append('');i+=1;continue
  if line.startswith('Table: '):flush();caption=line[7:].strip();i+=1;continue
  if line.startswith('|'):
   flush();j=i
   while j<len(lines) and lines[j].startswith('|'):j+=1
   out.append(table(lines[i:j],caption));out.append('');caption=None;i=j;continue
  m=re.match(r'^(- |\d+\. )(.*)',line)
  # CommonMark: an ordered list may interrupt prose only when it starts at 1.
  # Otherwise a wrapped year such as "2024. Apple ..." is paragraph text.
  if m and (not para or m.group(1) in ('- ', '1. ')):
   flush();env='enumerate' if m.group(1)[0].isdigit() else 'itemize';items=[]
   while i<len(lines) and (re.match(r'^(- |\d+\. )',lines[i]) or (lines[i].startswith('   ') and items)):
    mm=re.match(r'^(- |\d+\. )(.*)',lines[i])
    if mm:items.append(mm.group(2))
    else:items[-1]+=' '+lines[i].strip()
    i+=1
   out.append('\\begin{'+env+'}');out+=['\\item '+text(it) for it in items];out.append('\\end{'+env+'}');out.append('');continue
  if not line.strip():flush();i+=1;continue
  para.append(line.strip());i+=1
 flush();return '\n'.join(out)

def section(md,name):
 m=re.search(r'^## '+re.escape(name)+r'\n(.*?)(?=^## |\Z)',md,re.S|re.M)
 if not m:raise ValueError('Missing section '+name)
 return m.group(1).strip()

def authors(md):
 """Author lines: '- Given | Surname | email | affiliation keys | ORCID | corresponding'
 and affiliation lines: '- key: Department; Organisation; City; State; Country'."""
 block=section(md,'Authors');out=[];affils=[]
 for line in block.split('\n'):
  line=line.strip()
  if not line.startswith('- '):continue
  parts=[x.strip() for x in line[2:].split('|')]
  if len(parts)==1 and ':' in parts[0]:
   key,rest=parts[0].split(':',1);f=[x.strip() for x in rest.split(';')]
   div='\\orgdiv{'+text(f[0])+'}, ' if f[0] else ''
   affils.append('\\affil'+('*' if key.strip()=='1' else '')+'['+key.strip()+']{'+div+'\\orgname{'+text(f[1])+'}, \\orgaddress{\\city{'+text(f[2])+'}, \\state{'+text(f[3])+'}, \\country{'+text(f[4])+'}}}')
  else:
   given,sur,email,keys,orcid,role=parts
   star='*' if role=='corresponding' else ''
   out.append('\\author'+star+'['+keys+']{\\fnm{'+text(given)+'} \\sur{'+text(sur)+'}}\\email{'+plain(email)+'}')
 return '\n'.join(out+affils)

def main():
 md=(PAPER/'MANUSCRIPT.md').read_text(encoding='utf-8');rw=(PAPER/'RELATED_WORK.md').read_text(encoding='utf-8')
 related=re.search(r'^## 2 Related work\n(.*?)(?=^## Claims ledger)',rw,re.S|re.M).group(1)
 title=re.search(r'^# (.*)',md,re.M).group(1)
 short=re.search(r'^\*\*Short title\.\*\* (.*)',md,re.M).group(1)
 abstract=section(md,'Abstract');abstract=re.sub(r'^\*\(.*?\)\*\s*','',abstract,flags=re.S)
 abstract,kw=abstract.split('**Keywords.**');keywords=[k.strip().rstrip('.') for k in kw.strip().split(';')]
 main_md=md.split('## 1 Introduction',1)[1].split('## Declarations',1)[0]
 main_md='## 1 Introduction'+main_md.replace('<!-- include RELATED_WORK -->',related)
 declarations=md.split('## Declarations',1)[1]
 tex=['%% Generated by scripts/build_manuscript.py from docs/paper/MANUSCRIPT.md -- do not edit.',
  '\\documentclass[referee,lineno,pdflatex,sn-basic]{sn-jnl}',
  '\\usepackage{graphicx,booktabs,tabularx,amsmath,amssymb,xcolor,tikz,url}',
  '\\renewcommand{\\tabularxcolumn}[1]{>{\\raggedright\\arraybackslash}p{#1}}','\\usetikzlibrary{arrows.meta,positioning,fit}',
  '\\raggedbottom','\\begin{document}','\\title['+text(short)+']{'+text(title)+'}',
  authors(md),
  '\\abstract{'+text(' '.join(abstract.split()))+'}','\\keywords{'+', '.join(text(k) for k in keywords)+'}','\\maketitle','',
  body(main_md),'\\backmatter','\\section*{Declarations}','',body(declarations,level_shift=2),
  '\\bibliography{references}','\\end{document}']
 (PAPER/'manuscript.tex').write_text('\n'.join(tex)+'\n',encoding='utf-8')
 print('wrote',PAPER/'manuscript.tex')
 if '--pdf' in sys.argv:
  r=subprocess.run(['latexmk','-pdf','-interaction=nonstopmode','-halt-on-error','manuscript.tex'],cwd=PAPER,capture_output=True,text=True)
  log=(PAPER/'manuscript.log').read_text(encoding='utf-8',errors='replace') if (PAPER/'manuscript.log').exists() else ''
  undefined=sorted(set(re.findall(r"Citation `([^']+)' .*undefined",log)))
  print('latexmk exit',r.returncode,'| undefined citations:',undefined or 'none','| warnings:',log.count('LaTeX Warning'))
  if r.returncode:
   print(r.stdout[-3000:]);print(r.stderr[-3000:]);raise SystemExit(r.returncode)
  if undefined:raise SystemExit('Unresolved citations in manuscript')

if __name__=='__main__':main()
