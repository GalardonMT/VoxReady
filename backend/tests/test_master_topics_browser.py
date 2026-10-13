"""E2E de UI con Chrome temporal y endpoints reales sobre Azure SQL.

Requiere frontend/out generado, playwright y las dos variables opt-in.
No inicia sesión real en Entra ni invoca el análisis externo del worker.
Las altas de prueba se revierten mediante azure_api.
"""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import re
import threading
from urllib.parse import urlparse

import pytest
from test_master_topics_azure import azure_api  # noqa: F401

pytestmark = pytest.mark.skipif(os.getenv('VOXREADY_TEST_BROWSER') != '1', reason='Browser E2E is opt-in')
ROOT = Path(__file__).resolve().parents[2]


class StaticApp(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        path = urlparse(self.path).path
        target = Path(self.directory) / path.lstrip('/')
        if path.endswith('.txt') and not target.exists():
            alternate = Path(self.directory) / path.lstrip('/')[:-4] / 'index.txt'
            if alternate.exists():
                self.path = path[:-4] + '/index.txt'
        super().do_GET()


def test_master_ui_question_order_archive_and_speaker_catalog(azure_api):
    from playwright.sync_api import sync_playwright, expect
    expect.set_options(timeout=30000)
    client, current, cursor, seed = azure_api
    output = ROOT / 'frontend' / 'out'
    assert output.exists(), 'Run npm run build in frontend first'
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(StaticApp, directory=str(output)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    saved = {}
    origin = f'http://127.0.0.1:{server.server_port}'
    errors = []
    screenshots = ROOT / 'scratch'
    screenshots.mkdir(exist_ok=True)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='chrome', headless=True)
            page = browser.new_page(viewport={'width': 1440, 'height': 1050})
            page.set_default_timeout(60000)
            page.on('pageerror', lambda error: errors.append(str(error)))

            def api_route(route):
                request = route.request
                url = urlparse(request.url)
                path = url.path
                if not re.search(r'/(api/master|dev/token|scenarios|sessions)(/|$)', path):
                    route.continue_()
                    return
                headers = {'access-control-allow-origin': origin, 'access-control-allow-headers': '*',
                           'access-control-allow-methods': 'GET,POST,PUT,PATCH,OPTIONS', 'content-type': 'application/json'}
                if request.method == 'OPTIONS':
                    route.fulfill(status=200, headers=headers, body='{}')
                    return
                response = client.request(request.method, path + ('?' + url.query if url.query else ''),
                                          content=request.post_data_buffer, headers={k: v for k, v in request.headers.items() if k in ('content-type', 'authorization', 'idempotency-key')})
                if request.method == 'POST' and path.endswith('/api/master/topics') and response.status_code == 201:
                    saved['topic'] = response.json()
                if request.method == 'POST' and '/api/master/topics/' in path and path.endswith('/scenarios') and response.status_code == 201:
                    saved['scenario'] = response.json()
                if request.method == 'POST' and path.endswith('/sessions') and response.status_code == 201:
                    saved['session'] = response.json()
                route.fulfill(status=response.status_code, headers=headers, body=response.content)

            page.route('**/*', api_route)
            try:
                page.goto(origin + '/login/')
                page.get_by_role('button', name=re.compile('Elena Díaz')).click()
                expect(page.get_by_role('button', name=re.compile('Catálogo de temas'))).to_be_visible()
                page.get_by_role('button', name=re.compile('Catálogo de temas')).click()
                expect(page.get_by_text('Retiro de producto del mercado', exact=True)).to_be_visible()
                page.get_by_role('button', name='+ Crear Nuevo Tema', exact=True).click()
                page.get_by_label('Nombre del tema', exact=False).fill('Prueba UI de 12 preguntas')
                page.get_by_label('Contexto de la crisis', exact=False).fill('Contexto institucional de prueba en transacción reversible.')
                for number in range(1, 13):
                    page.get_by_role('textbox', name='Agregar Banco de preguntas', exact=True).fill(f'Pregunta UI {number}')
                    page.get_by_role('textbox', name='Agregar Banco de preguntas', exact=True).press('Enter')
                expect(page.get_by_role('heading', name='Banco de preguntas (12)', exact=True)).to_be_visible()
                page.get_by_role('button', name='Guardar tema', exact=True).click()
                expect(page.get_by_role('button', name='+ Crear Escenario', exact=True)).to_be_enabled()
                page.get_by_role('button', name='+ Crear Escenario', exact=True).click()
                form = page.get_by_role('form', name='Editor de temas y escenarios', exact=True)
                form.get_by_label('Título del escenario', exact=False).fill('Escenario UI ordenado')
                form.get_by_role('button', name='Operativa', exact=True).click()
                form.get_by_role('button', name='Fácil', exact=True).click()
                form.get_by_label('Duración estimada', exact=False).fill('7')
                form.get_by_label('Cliente asignado', exact=False).select_option(label='Cliente Demo VoxReady')
                for index in (9, 2, 11, 0):
                    form.get_by_role('button', name='+ Agregar', exact=True).nth(index).click()
                form.get_by_role('button', name='Subir pregunta 2', exact=True).click()
                form.get_by_role('button', name='Bajar pregunta 3', exact=True).click()
                selected = form.locator('.master-selected')
                expect(selected.locator('li').nth(0)).to_contain_text('Pregunta UI 3')
                expect(selected.locator('li').nth(1)).to_contain_text('Pregunta UI 10')
                expect(selected.locator('li').nth(2)).to_contain_text('Pregunta UI 1')
                expect(selected.locator('li').nth(3)).to_contain_text('Pregunta UI 12')
                page.screenshot(path=str(screenshots / 'master-editor.png'), full_page=True)
                form.get_by_role('button', name='Guardar escenario', exact=True).click()
                expect(form).not_to_be_visible()
                page.get_by_role('button', name='← Volver al catálogo', exact=True).click()
                row = page.get_by_role('row').filter(has_text='Prueba UI de 12 preguntas')
                expect(row).to_be_visible()
                row.get_by_role('button', name=re.compile('Archivar')).click()
                dialog = page.get_by_role('dialog')
                expect(dialog).to_contain_text('archivará automáticamente todos sus escenarios asociados')
                dialog.get_by_role('button', name='Cancelar', exact=True).click()
                expect(row).to_be_visible()
                row.get_by_role('button', name=re.compile('Archivar')).click()
                page.get_by_role('dialog').get_by_role('button', name='Archivar', exact=True).click()
                expect(row).not_to_be_visible()
                page.get_by_role('button', name='Archivados', exact=True).click()
                expect(row).to_be_visible()
                row.get_by_role('button', name=re.compile('Reactivar')).click()
                expect(row).not_to_be_visible()
                page.get_by_role('button', name='Activos', exact=True).click()
                expect(row).to_be_visible()
                page.screenshot(path=str(screenshots / 'master-catalog.png'), full_page=True)
                assert saved['scenario']['questionCount'] == 4
                current['label'] = 'speaker'
                page.get_by_role('button', name=re.compile('Salir')).click()
                page.get_by_role('button', name=re.compile('Ana Torres')).click()
                page.get_by_role('button', name=re.compile('Catálogo$')).click()
                card = page.locator('.card').filter(has=page.get_by_role('heading', name='Escenario UI ordenado', exact=True))
                expect(card).to_contain_text('Fácil')
                expect(card).to_contain_text('Dirección')
                card.get_by_role('button', name='Empezar', exact=True).click()
                expect(page.get_by_role('button', name=re.compile('Comenzar sesión'))).to_be_visible()
                setup = client.get('/sessions/' + saved['session']['sessionId']).json()
                assert [q['text'] for q in setup['questions']] == ['Pregunta UI 3', 'Pregunta UI 10', 'Pregunta UI 1', 'Pregunta UI 12']
                assert not errors, errors
            except Exception:
                page.screenshot(path=str(screenshots / 'master-ui-failure.png'), full_page=True)
                raise
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
