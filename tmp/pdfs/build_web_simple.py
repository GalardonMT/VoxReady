from pathlib import Path

helpers=Path('tmp/pdfs/build_vision_diagram.py').read_text(encoding='utf-8').split("text(60,52,")[0]
helpers=helpers.replace('W,H=1800,1080','W,H=1900,1190').replace('VoxReady_Vision_C4_Nivel3','VoxReady_Web_C4_Simplificado').replace('voxready-vision','aplicación web simplificada').replace('vision-c4','web-simple-c4')
exec(helpers)

def card(x,y,w,title,tech,desc,external=False):
    rect(x,y,w,145,'#e1e5eb' if external else '#d7f8f3','#68727e' if external else '#10a89b')
    fs=min(24,24*(w-24)/pdfmetrics.stringWidth(title,'ArialBold',24))
    text(x+w/2,y+38,title,fs,True)
    text(x+w/2,y+72,tech,17,True,'#596675' if external else '#008878')
    text(x+w/2,y+110,desc,19)

def connector(points):
    global counter
    c.setStrokeColor(HexColor('#56636b'));c.setLineWidth(1.8)
    p=c.beginPath();p.moveTo(points[0][0],H-points[0][1])
    for x,y in points[1:]:p.lineTo(x,H-y)
    c.drawPath(p)
    svg.append(f'<polyline points="{" ".join(f"{x},{y}" for x,y in points)}" fill="none" stroke="#56636b" stroke-width="1.8"/>')
    counter+=1
    e=ET.SubElement(root,'mxCell',id=str(counter+1),style='endArrow=none;strokeColor=#56636b;strokeWidth=1.8;',edge='1',parent='1')
    g=ET.SubElement(e,'mxGeometry',relative='1',attrib={'as':'geometry'})
    ET.SubElement(g,'mxPoint',x=str(points[0][0]),y=str(points[0][1]),attrib={'as':'sourcePoint'})
    ET.SubElement(g,'mxPoint',x=str(points[-1][0]),y=str(points[-1][1]),attrib={'as':'targetPoint'})
    if len(points)>2:
        a=ET.SubElement(g,'Array',attrib={'as':'points'})
        for x,y in points[1:-1]:ET.SubElement(a,'mxPoint',x=str(x),y=str(y))

text(50,56,'VoxReady · C4 nivel 3',34,True,anchor='start')
text(50,94,'Aplicación web | Componentes y flujos principales',24,anchor='start')

rect(270,150,1230,900,'#fbfefe','#7c9295',10)
text(300,190,'Aplicación Web',26,True,anchor='start')
text(300,220,'Next.js / React / TypeScript · Ejecutada en el navegador',19,color='#647078',anchor='start')

card(20,280,195,'Usuarios','[Personas]','Tres roles',True)
card(320,280,300,'Navegación','[Componente · React]','Organiza las vistas por rol')
card(1060,280,340,'Autenticación','[Componente · MSAL]','Gestiona sesión y acceso')
card(1580,280,290,'Microsoft Entra ID','[Sistema externo]','Autentica al usuario',True)

card(320,570,300,'Prácticas y grabación','[React / MediaRecorder]','Prepara y graba la sesión')
card(710,570,300,'Informes y progreso','[Componente · React]','Consulta resultados y videos')
card(1100,570,300,'Administración','[Componente · React]','Gestiona temas y contenidos')
card(1580,570,290,'Azure Blob Storage','[Almacenamiento]','Conserva los videos',True)

card(710,860,690,'Servicios de aplicación','[Componente lógico · TypeScript / Fetch]','Accede a la API y transfiere archivos')
card(1580,860,290,'API Backend','[Contenedor · FastAPI]','Expone los datos y servicios',True)

edge([(215,352),(320,352)],[(266,330,'Usa')])
edge([(620,352),(1060,352)],[(840,329,'Consulta sesión y rol')])
edge([(1400,352),(1580,352)],[(1490,328,'Login · HTTPS')])

connector([(470,425),(470,500),(1250,500)])
for x in [470,860,1250]:edge([(x,500),(x,570)])
text(860,482,'Abre las vistas',19,True)

for x in [470,860,1250]:connector([(x,715),(x,785)])
connector([(470,785),(1250,785)])
edge([(1055,785),(1055,860)],[(1195,833,'Solicita operaciones')])

edge([(1400,900),(1470,900),(1470,642),(1580,642)],[(1485,613,'Sube videos'),(1485,637,'HTTPS / SAS')])
edge([(1400,967),(1580,967)],[(1490,940,'HTTP(S) / JSON')])

text(300,1092,'Verde: componentes de la web. Gris: actores y dependencias externas.',19,color='#596675',anchor='start')
text(300,1122,'Flechas: llamadas principales; incluyen sus respuestas. Relaciones internas: React / JavaScript.',19,color='#596675',anchor='start')
text(300,1154,'Base: main @ 5d3e37f · Se agrupan responsabilidades y se omiten relaciones secundarias.',17,color='#647078',anchor='start')

c.showPage();c.save()
svg.append('</svg>');base.with_suffix('.svg').write_text('\n'.join(svg),encoding='utf-8')
ET.ElementTree(mx).write(base.with_suffix('.drawio'),encoding='utf-8',xml_declaration=True)
print(base.resolve())
