from pathlib import Path
import html, math, subprocess, xml.etree.ElementTree as ET
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor

OUT=Path('output/pdf'); OUT.mkdir(parents=True, exist_ok=True)
W,H=1800,1080
base=OUT/'VoxReady_Vision_C4_Nivel3'
pdfmetrics.registerFont(TTFont('Arial',r'C:/Windows/Fonts/arial.ttf'))
pdfmetrics.registerFont(TTFont('ArialBold',r'C:/Windows/Fonts/arialbd.ttf'))
c=canvas.Canvas(str(base.with_suffix('.pdf')),pagesize=(W,H))
c.setTitle('VoxReady - C4 nivel 3 - Componentes de voxready-vision')
svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}"><rect width="100%" height="100%" fill="white"/>']
mx=ET.Element('mxfile',host='app.diagrams.net',version='24.7.17')
diagram=ET.SubElement(mx,'diagram',name='C4 - voxready-vision',id='vision-c4')
model=ET.SubElement(diagram,'mxGraphModel',dx=str(W),dy=str(H),grid='1',gridSize='10',page='1',pageScale='1',pageWidth=str(W),pageHeight=str(H))
root=ET.SubElement(model,'root'); ET.SubElement(root,'mxCell',id='0');ET.SubElement(root,'mxCell',id='1',parent='0')
counter=0
def cell(value,style,x,y,w,h):
 global counter
 counter+=1
 e=ET.SubElement(root,'mxCell',id=str(counter+1),value=value,style=style,vertex='1',parent='1')
 ET.SubElement(e,'mxGeometry',x=str(x),y=str(y),width=str(w),height=str(h),attrib={'as':'geometry'})
 return e
def rect(x,y,w,h,fill,stroke='#10a89b',radius=8,dashed=False,drawio=True):
 c.setFillColor(HexColor(fill));c.setStrokeColor(HexColor(stroke));c.setLineWidth(1.6)
 c.setDash([7,5] if dashed else [])
 c.roundRect(x,H-y-h,w,h,radius,fill=1,stroke=1)
 c.setDash([])
 dash='stroke-dasharray="7 5"' if dashed else ''
 svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="1.6" {dash}/>')
 if drawio: cell('',f'rounded=1;arcSize=3;fillColor={fill};strokeColor={stroke};dashed={int(dashed)};',x,y,w,h)
def text(x,y,s,size=18,bold=False,color='#233238',anchor='middle',drawio=True):
 font='ArialBold' if bold else 'Arial'
 c.setFont(font,size);c.setFillColor(HexColor(color))
 (c.drawCentredString if anchor=='middle' else c.drawString)(x,H-y,s)
 svg.append(f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-family="Arial, sans-serif" font-size="{size}" font-weight="{700 if bold else 400}" fill="{color}">{html.escape(s)}</text>')
 if drawio:
  width=pdfmetrics.stringWidth(s,font,size)+20
  cell(html.escape(s),f'text;html=1;align={"center" if anchor=="middle" else "left"};verticalAlign=middle;whiteSpace=wrap;rounded=0;fontFamily=Arial;fontSize={size};fontStyle={int(bold)};fontColor={color};',x-width/2 if anchor=='middle' else x,y-size,width,size+8)
def block(x,y,w,h,title,tech,lines,external=False):
 rect(x,y,w,h,'#e1e5eb' if external else '#d7f8f3','#68727e' if external else '#10a89b')
 title_size=min(22,22*(w-24)/pdfmetrics.stringWidth(title,'ArialBold',22))
 text(x+w/2,y+33,title,title_size,True)
 text(x+w/2,y+62,tech,16,True,'#596675' if external else '#008878')
 for i,line in enumerate(lines): text(x+w/2,y+100+i*25,line,18)
def edge(points,labels=None,dashed=False):
 global counter
 c.setStrokeColor(HexColor('#56636b'));c.setLineWidth(1.8);c.setDash([6,4] if dashed else [])
 p=c.beginPath();p.moveTo(points[0][0],H-points[0][1])
 for x,y in points[1:]:p.lineTo(x,H-y)
 c.drawPath(p);c.setDash([])
 x,y=points[-1];px,py=points[-2];ang=math.atan2(y-py,x-px)
 arr=[(x,y),(x-11*math.cos(ang-.45),y-11*math.sin(ang-.45)),(x-11*math.cos(ang+.45),y-11*math.sin(ang+.45))]
 p=c.beginPath();p.moveTo(arr[0][0],H-arr[0][1])
 for ax,ay in arr[1:]:p.lineTo(ax,H-ay)
 p.close();c.setFillColor(HexColor('#56636b'));c.drawPath(p,fill=1,stroke=0)
 dash='stroke-dasharray="6 4"' if dashed else ''
 svg.append(f'<polyline points="{" ".join(f"{x},{y}" for x,y in points)}" fill="none" stroke="#56636b" stroke-width="1.8" {dash}/>')
 svg.append(f'<polygon points="{" ".join(f"{x},{y}" for x,y in arr)}" fill="#56636b"/>')
 counter+=1
 e=ET.SubElement(root,'mxCell',id=str(counter+1),style=f'endArrow=block;endFill=1;strokeColor=#56636b;strokeWidth=1.8;dashed={int(dashed)};',edge='1',parent='1')
 g=ET.SubElement(e,'mxGeometry',relative='1',attrib={'as':'geometry'})
 ET.SubElement(g,'mxPoint',x=str(points[0][0]),y=str(points[0][1]),attrib={'as':'sourcePoint'})
 ET.SubElement(g,'mxPoint',x=str(x),y=str(y),attrib={'as':'targetPoint'})
 if len(points)>2:
  a=ET.SubElement(g,'Array',attrib={'as':'points'})
  for px,py in points[1:-1]:ET.SubElement(a,'mxPoint',x=str(px),y=str(py))
 for lx,ly,label in labels or []: text(lx,ly,label,16,True)

text(60,52,'VoxReady | Arquitectura C4 - Nivel 3',32,True,anchor='start')
text(60,88,'Componentes del contenedor voxready-vision (Worker de visión)',23,False,anchor='start')
text(60,119,'Revisión estática de main en GitHub · 22 octubre 2026 · Python 3.11 / FastAPI / MediaPipe',17,False,'#647078',anchor='start')

rect(390,160,1100,700,'#fbfefe','#7c9295',10)
text(420,193,'voxready-vision',24,True,anchor='start')
text(420,220,'[Contenedor: microservicio HTTP / Docker / Uvicorn :8000]',17,False,'#647078',anchor='start')

block(30,365,300,230,'Worker de análisis','[Contenedor externo al alcance]',[
 'Python / VisionClient','Prepara imágenes con FFmpeg.','Extrae a 2 FPS y selecciona','hasta 120 fotogramas.','Consume las métricas visuales.'])
block(440,350,300,220,'API de análisis visual','[Componente: FastAPI]',[
 'Recibe archivos multipart.','Coordina el análisis por lote','o por imagen individual.','Devuelve métricas en JSON.'])
text(590,550,'main.py',15,False,'#008878')
block(840,260,300,210,'Motor de análisis VISUM','[Componente lógico: MediaPipe]',[
 'Decodifica bytes con OpenCV.','Convierte BGR a RGB.','Infiere rostro y postura.','Deriva mirada, hombros y manos.'])
block(840,600,300,200,'Agregador de métricas','[Componente lógico: NumPy]',[
 'Filtra imágenes decodificables.','Calcula porcentajes, estabilidad','de hombros y balanceo del torso.','Entrega el resumen del lote.'])
block(1200,260,250,210,'Runtime y modelos','[Componente lógico: Python]',[
 'Inicializa Solutions o Tasks.','Carga FaceMesh y Pose,','o Face/Pose Landmarker.','Reutiliza archivos locales.'])
block(1540,260,230,210,'Google Cloud Storage','[Sistema externo / HTTPS]',[
 'Distribuye artefactos','MediaPipe preentrenados:','face_landmarker.task','pose_landmarker_lite.task'],True)

edge([(330,405),(440,405)],[(385,324,'POST multipart'),(385,346,'/analyze/batch')])
edge([(440,515),(330,515)],[(383,615,'Respuesta JSON'),(383,637,'summary + frame_details')])
text(180,651,'HTTP(S), según URL configurada',16,False,'#596675')
text(180,675,'Alternativa: POST /analyze-frame',16,False,'#596675')

edge([(590,350),(590,297),(840,297)],[(687,269,'Analiza cada imagen'),(687,289,'bytes / métricas')])
edge([(590,570),(590,698),(840,698)],[(689,649,'Solicita agregado'),(689,672,'lista / resumen')])
edge([(1140,365),(1200,365)],[(1170,506,'Usa detectores'),(1170,528,'en memoria')])
edge([(1450,365),(1540,365)],[(1510,210,'Descarga HTTPS'),(1510,232,'solo si faltan modelos')],True)

text(590,762,'GET /health: estado, versión y runtime',16,False,'#596675')
text(590,787,'Lote: procesa las imágenes secuencialmente',16,False,'#596675')
text(420,835,'Descomposición lógica de core/analyzer.py: clase MultimodalVisionAnalyzer y función auxiliar de descarga.',17,False,'#596675',anchor='start')
text(1550,528,'Descarga condicional:',17,True,anchor='start')
text(1550,554,'solo runtime Tasks.',17,False,anchor='start')
text(1550,580,'Inferencia dentro del',17,False,anchor='start')
text(1550,605,'contenedor de visión.',17,False,anchor='start')

rect(30,895,1740,130,'#f5f8fa','#d4dde1',8)
text(55,926,'Lectura del diagrama',18,True,anchor='start')
text(55,955,'Verde: componente o contenedor propio. Gris: sistema externo. Borde grande: límite del contenedor que se descompone.',17,False,anchor='start')
text(55,981,'Flecha continua: llamada o respuesta indicada; las llamadas internas son Python en memoria. Flecha discontinua: dependencia condicional de inicio.',17,False,anchor='start')
text(55,1007,'Alcance: inferencia visual y métricas. FFmpeg, reintentos HTTP, fusión multimodal, informe y persistencia pertenecen al worker de análisis.',17,False,anchor='start')
text(60,1057,'Fuente: GalardonMT/VoxReady · Archivos contrastados con main remoto; coinciden con origin/main c076677. Ejecución no validada.',16,False,'#647078',anchor='start')
c.showPage();c.save()
svg.append('</svg>');base.with_suffix('.svg').write_text('\n'.join(svg),encoding='utf-8')
ET.ElementTree(mx).write(base.with_suffix('.drawio'),encoding='utf-8',xml_declaration=True)
print(base.resolve())
