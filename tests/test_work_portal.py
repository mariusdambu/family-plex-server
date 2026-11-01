import pathlib
import tempfile
import unittest
import json
import io
from unittest.mock import Mock
import work_portal as w


class WorkPortalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        (self.root / 'Project').mkdir()
        (self.root / 'Project/index.html').write_text('<html>Test</html>')
        (self.root / 'Project/app.js').write_text('console.log(1)')
        (self.root / 'Project/private.json').write_text('{}')

    def tearDown(self):
        self.tmp.cleanup()

    def test_web_assets_allowed(self):
        self.assertEqual(w.asset(self.root, 'Project/app.js').name, 'app.js')

    def test_private_files_not_published(self):
        for path in ['Project/private.json', '../index.html', 'Project/../Project/index.html', 'Project/.secret.html']:
            with self.assertRaises(ValueError):
                w.asset(self.root, path)

    def test_symlink_denied(self):
        (self.root / 'Project/linked.html').symlink_to(self.root / 'Project/index.html')
        with self.assertRaises(ValueError):
            w.asset(self.root, 'Project/linked.html')

    def test_metadata_selects_existing_logo(self):
        project = self.root / 'Project'
        (project / 'assets').mkdir()
        (project / 'assets/brand.png').write_bytes(b'test')
        (project / 'portal.json').write_text(json.dumps({'logo': 'assets/brand.png'}))
        self.assertEqual(w.project_logo(project), '/work/Project/assets/brand.png')
        card = w.project_card(project)
        self.assertIn('<img ', card)
        self.assertNotIn('<h2>', card)
        self.assertIn('aria-label="Project"', card)
        with self.assertRaises(ValueError):
            w.asset(self.root, 'Project/portal.json')

    def test_conventional_logo(self):
        project = self.root / 'Project'
        (project / 'assets').mkdir()
        (project / 'assets/logo.svg').write_text('<svg/>')
        self.assertEqual(w.project_logo(project), '/work/Project/assets/logo.svg')

    def test_local_project_can_reuse_vector_icon(self):
        project = self.root / 'Project'
        (project / 'portal.json').write_text(json.dumps({'name': 'Sample Utilities', 'icon': 'command-bridge'}))
        card = w.project_card(project)
        self.assertIn('href="/work/Project/index.html"', card)
        self.assertIn('external-logo', card)
        self.assertIn('aria-label="Sample Utilities"', card)
        self.assertNotIn('github.io', card)

    def test_docx_download_is_opt_in_and_other_documents_stay_private(self):
        project = self.root / 'Project'
        doc = project / 'Example template.docx'
        doc.write_bytes(b'PK-test-document')
        (project / 'private.docx').write_bytes(b'private')
        with self.assertRaises(ValueError):
            w.asset(self.root, 'Project/Example template.docx')
        (project / 'portal.json').write_text(json.dumps({'downloads': [doc.name]}))
        self.assertEqual(w.asset(self.root, 'Project/' + doc.name), doc.resolve())
        with self.assertRaises(ValueError):
            w.asset(self.root, 'Project/private.docx')
        handler = Mock(path='/work/Project/Example%20template.docx', wfile=io.BytesIO())
        w.serve(handler, self.root)
        handler.send_response.assert_called_once_with(200)
        headers = dict(call.args for call in handler.send_header.call_args_list)
        self.assertEqual(headers['Content-Type'], 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        self.assertIn("filename*=UTF-8''Example%20template.docx", headers['Content-Disposition'])
        self.assertEqual(handler.wfile.getvalue(), b'PK-test-document')

    def test_declared_install_entry_without_duplicate_index(self):
        project = self.root / 'Project'
        (project / 'index.html').unlink()
        (project / 'install.html').write_text('<html>Install</html>')
        (project / 'portal.json').write_text(json.dumps({'entry': 'install.html'}))
        self.assertEqual(w.project_entry(project), 'install.html')
        self.assertIn('href="/work/Project/install.html"', w.project_card(project))
        self.assertEqual(w.asset(self.root, 'Project/app.js'), (project / 'app.js').resolve())
        self.assertFalse((project / 'index.html').exists())

    def test_entry_cannot_escape_project(self):
        project = self.root / 'Project'
        for entry in ['../Project/index.html', '/index.html', '.secret.html', 'file.json']:
            (project / 'portal.json').write_text(json.dumps({'entry': entry}))
            self.assertIsNone(w.project_entry(project))

    def test_invalid_logo_cannot_escape_project(self):
        project = self.root / 'Project'
        (project / 'portal.json').write_text(json.dumps({'logo': '../private.png'}))
        self.assertIsNone(w.project_logo(project))
        self.assertIn('<svg ', w.project_card(project))

    def test_external_cards_use_secure_links_and_original_vectors(self):
        (self.root / '.portal-links.json').write_text(json.dumps([
            {'name': 'Sample Utilities', 'url': 'https://example.github.io/bridge/', 'icon': 'command-bridge'},
            {'name': 'Guide', 'url': 'https://example.github.io/guide/', 'icon': 'autopilot'},
            {'name': 'CV', 'url': 'https://example.github.io/', 'icon': 'cv'}]))
        cards = w.external_cards(self.root)
        self.assertEqual(cards.count('class="card"'), 3)
        self.assertEqual(cards.count('<svg '), 3)
        self.assertIn('rel="noopener noreferrer"', cards)

    def test_unsafe_external_links_are_rejected(self):
        (self.root / '.portal-links.json').write_text(json.dumps([
            {'url': 'javascript:alert(1)'}, {'url': 'http://example.invalid'},
            {'url': 'https://user:password@example.invalid/'}, {'url': 'https://['}]))
        self.assertEqual(w.external_cards(self.root), '')

    def test_missing_or_invalid_link_catalogue_is_ignored(self):
        self.assertEqual(w.external_cards(self.root), '')

    def test_nested_project_assets_and_local_card(self):
        project = self.root / 'Group/Guide'
        project.mkdir(parents=True)
        (project / 'index.html').write_text('<html>Guide</html>')
        (project / 'style.css').write_text('body{}')
        (self.root / 'Group/private.html').write_text('private')
        self.assertEqual(w.asset(self.root, 'Group/Guide/style.css'), (project / 'style.css').resolve())
        with self.assertRaises(ValueError):
            w.asset(self.root, 'Group/private.html')
        (self.root / '.portal-links.json').write_text(json.dumps([
            {'name': 'Guide', 'url': '/work/Group/Guide/index.html', 'icon': 'autopilot'}]))
        card = w.external_cards(self.root)
        self.assertIn('/work/Group/Guide/index.html', card)
        self.assertNotIn('target="_blank"', card)

    def test_local_link_cannot_traverse_or_publish_private_files(self):
        (self.root / '.portal-links.json').write_text(json.dumps([
            {'url': '/work/Project/private.json'},
            {'url': '/work/Project/../../private.html'},
            {'url': '//attacker.invalid/work/Project/index.html'}]))
        self.assertEqual(w.external_cards(self.root), '')
        (self.root / '.portal-links.json').write_text('invalid')
        self.assertEqual(w.external_cards(self.root), '')
