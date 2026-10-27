from pathlib import Path

# Reuse only the drawing primitives; keep the earlier vision artifact unchanged.
helpers=Path('tmp/pdfs/build_vision_diagram.py').read_text(encoding='utf-8').split("text(60,52,")[0]
helpers=helpers.replace('W,H=1800,1080','W,H=2330,1580').replace('VoxReady_Vision_C4_Nivel3','VoxReady_Web_C4_Nivel3').replace('voxready-vision','aplicación web').replace('vision-c4','web-c4')
helpers=helpers.replace('for lx,ly,label in labels or []: text(lx,ly,label,16,True)','for lx,ly,caption in labels or []: label(lx,ly,caption)')
exec(helpers)

def note(x,y,s): text(x,y,s,17,False,'#647078')
def label(x,y,s,size=16):
    width=pdfmetrics.stringWidth(s,'ArialBold',size)+12
    c.setFillColor(HexColor('#ffffff'));c.rect(x-width/2,H-y-4,width,size+8,fill=1,stroke=0)
    svg.append(f'<rect x="{x-width/2}" y="{y-size-4}" width="{width}" height="{size+8}" fill="white"/>')
    cell('','fillColor=#ffffff;strokeColor=none;',x-width/2,y-size-4,width,size+8)
    text(x,y,s,size,True)
def line(points):
    c.setStrokeColor(HexColor('#56636b'));c.setLineWidth(1.8)
    p=c.beginPath();p.moveTo(points[0][0],H-points[0][1])
    for x,y in points[1:]:p.lineTo(x,H-y)
    c.drawPath(p)
    svg.append(f'<polyline points="{" ".join(f"{x},{y}" for x,y in points)}" fill="none" stroke="#56636b" stroke-width="1.8"/>')
    global counter
    counter+=1
    e=ET.SubElement(root,'mxCell',id=str(counter+1),style='endArrow=none;strokeColor=#56636b;strokeWidth=1.8;',edge='1',parent='1')
    g=ET.SubElement(e,'mxGeometry',relative='1',attrib={'as':'geometry'})
    ET.SubElement(g,'mxPoint',x=str(points[0][0]),y=str(points[0][1]),attrib={'as':'sourcePoint'})
    ET.SubElement(g,'mxPoint',x=str(points[-1][0]),y=str(points[-1][1]),attrib={'as':'targetPoint'})
    if len(points)>2:
        arr=ET.SubElement(g,'Array',attrib={'as':'points'})
        for x,y in points[1:-1]: ET.SubElement(arr,'mxPoint',x=str(x),y=str(y))

text(45,53,'VoxReady | Arquitectura C4 - Nivel 3',34,True,anchor='start')
text(45,91,'Componentes de la aplicación web · frontend',25,anchor='start')
text(45,123,'main remoto: 5d3e37f · 22 octubre 2026 · Next.js 16.3.4 / React 19.2.8 / TypeScript',18,color='#647078',anchor='start')

rect(240,160,1620,1195,'#fbfefe','#7c9295',10)
text(270,196,'Aplicación Web VoxReady',25,True,anchor='start')
text(270,225,'[Contenedor C4: aplicación estática en el navegador; exportada por Next.js y servida por Nginx]',18,color='#647078',anchor='start')

block(20,280,180,185,'Usuarios','[Personas]', ['Vocero','Admin. del cliente','Configurador maestro'],True)
block(280,270,330,200,'Navegación y composición','[Componente: Next.js / React]',[
 'Selecciona vistas y conserva','el estado del flujo de práctica.','Rutas por rol; tema e idiomas.'])
note(445,448,'app/* · ThemeContext · I18nContext')
block(940,270,360,200,'Identidad y acceso a vistas','[Componente: React / MSAL]',[
 'Login, token y perfil del usuario.','Control visual de rutas por rol.','Microsoft Entra o Dev Auth.'])
note(1120,448,'AuthContext · MsalWrapper · ProtectedRoute')
block(1990,270,280,200,'Microsoft Entra ID','[Sistema externo]',[
 'Inicio y cierre de sesión.','Entrega tokens mediante MSAL.','Redirecciones del navegador.'],True)

block(280,650,310,230,'Preparación de la práctica','[Componente: React]',[
 'Catálogo de escenarios.','Crea sesión y carga preguntas.','Chequeo de cámara y micrófono.','Consentimiento para grabar.'])
note(435,858,'ScenarioCatalog · TechConsentView')
block(690,650,310,230,'Grabación y entrevista','[Componente: React / Web APIs]',[
 'MediaRecorder y getUserMedia.','Pausa, cancelación y turnos.','Avatar 3D con Three.js.','Lectura con speechSynthesis.'])
note(845,858,'LiveSessionView · InterviewerAvatar')
block(1100,650,310,230,'Resultados y aprendizaje','[Componente: React / HTML5]',[
 'Consulta del análisis cada 5 s.','Informes coach y Visum.','Historial, videos y microlecciones.','Reproductor con línea de tiempo.'])
note(1255,858,'Analyzing / Report / Progress / Lesson')
block(1510,650,310,230,'Administración y maestro','[Componente: React]',[
 'Panel del cliente y temas.','Temas, escenarios y preguntas.','Gestión de microlecciones.','Retención, rúbrica y etiquetas*.'])
note(1665,858,'client-admin/* · master/*')
block(1990,650,280,230,'Azure Blob Storage','[Contenedor de datos externo]',[
 'Grabaciones de las prácticas.','Videos de microlecciones.','Carga y lectura directa','con URL SAS temporal.'],True)

block(690,1060,560,220,'Servicios de dominio y transferencia','[Componente lógico: módulos TypeScript]',[
 'Gestionan sesiones, consentimiento, informes y contenidos.','Obtienen URLs SAS y notifican la finalización de la sesión.','Suben grabaciones y microlecciones directamente a Blob.'])
note(970,1238,'sessionFlowService · sessionService · topicService')
note(970,1264,'masterTopicService · microlessonService · progressService')
block(1510,1060,310,220,'Cliente HTTP de la API','[Componente: Fetch API]',[
 'Resuelve el token de acceso.','Añade Bearer y correlación.','Normaliza errores HTTP y red.','Envía JSON a la API.'])
note(1665,1264,'apiClient.ts · apiFetch')
block(1990,1060,280,220,'API Backend','[Contenedor: FastAPI]',[
 'Perfil y servicios de negocio.','Emite URLs SAS temporales.','Recibe aviso de finalización.','Expone informes y contenidos.'],True)

edge([(200,370),(280,370)],[(240,345,'Usa')])
edge([(610,365),(940,365)],[(775,336,'Consulta sesión y rol'),(775,389,'Contexto React')])
edge([(1300,320),(1990,320)],[(1645,289,'Autentica / obtiene token · HTTPS / MSAL')])

# Shared connectors denote several calls from the same component, not a message bus.
line([(445,470),(445,570)])
line([(435,570),(1665,570)])
for xx in [435,845,1255,1665]: edge([(xx,570),(xx,650)])
text(1000,547,'Compone vistas e intercambia estado y callbacks (React)',18,True)

for xx in [435,845,1255,1665]: line([(xx,880),(xx,990)])
line([(435,990),(1665,990)])
edge([(970,990),(970,1060)],[(970,1032,'Invoca operaciones / recibe datos')])
label(435,938,'Sesión y consentimiento')
label(845,938,'SAS y finalización')
label(1255,968,'Informes y contenidos')
label(1665,968,'Gestión conectada*')

edge([(1250,1140),(1510,1140)],[(1380,1113,'Invoca apiFetch'),(1380,1168,'Promise / JSON')])
edge([(1820,1170),(1990,1170)],[(1905,1200,'HTTP(S) / JSON'),(1905,1222,'Bearer + correlación')])

# AuthContext uses fetch directly for profile and Dev Auth; it bypasses apiFetch.
edge([(1300,420),(1910,420),(1910,1100),(1990,1100)],[(1640,398,'Consulta perfil /me; Dev Auth: /dev/token'),(1640,447,'fetch directo · HTTP(S) / JSON')])

# Binary traffic goes directly to Blob, not through the API transport component.
edge([(1410,740),(1450,740),(1450,915),(1960,915),(1960,730),(1990,730)],[(1680,900,'GET de video · HTTPS / SAS')])
edge([(1250,1210),(1330,1210),(1330,1320),(1940,1320),(1940,820),(1990,820)],[(1640,1310,'PUT binario directo · HTTPS / SAS · BlockBlob')])

rect(30,1390,2270,135,'#f5f8fa','#d4dde1',8)
text(55,1420,'Cómo leerlo',20,True,anchor='start')
text(55,1450,'Verde: componentes de VoxReady. Gris: personas, servicios y contenedores fuera del alcance. Las llamadas internas son JavaScript/React en memoria.',18,anchor='start')
text(55,1478,'Las líneas compartidas agrupan dependencias de varias vistas; no representan colas. Las respuestas se incluyen en la relación de llamada.',18,anchor='start')
text(55,1506,'* Retención, rúbrica y etiquetado tienen vistas locales o de ejemplo; no se dibujan como operaciones persistidas. La integración conectada se detalla en las notas.',18,anchor='start')
text(45,1557,'Fuente: GalardonMT/VoxReady, main @ 5d3e37f2e2243a9b9cd7dfa6d61a0529a0b24db2. Revisión estática; ejecución y despliegue no validados.',17,color='#647078',anchor='start')
c.showPage();c.save()
svg.append('</svg>');base.with_suffix('.svg').write_text('\n'.join(svg),encoding='utf-8')
ET.ElementTree(mx).write(base.with_suffix('.drawio'),encoding='utf-8',xml_declaration=True)
print(base.resolve())
