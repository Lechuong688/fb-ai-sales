"""Render the real application shell with an isolated, temporary database."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import tempfile
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication
import backend.database.db as database

temp = tempfile.TemporaryDirectory()
database.engine = create_engine('sqlite:///' + str(Path(temp.name) / 'preview.db'))
database.SessionLocal = sessionmaker(bind=database.engine, expire_on_commit=False)
from frontend.main import load_styles
from frontend.main_window import MainWindow
from backend.database.models.account import Account

app = QApplication([])
for name in ('segoeui.ttf', 'segoeuib.ttf', 'seguiemj.ttf'):
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/' + name)
app.setStyle('Fusion')
app.setFont(QFont('Segoe UI', 10))
load_styles(app, Path('frontend'))
database.Base.metadata.create_all(database.engine)
with database.SessionLocal() as session:
    session.add(Account(name='Bếp Chương', uid='100000000001', profile='demo-shop'))
    session.add(Account(name='Thiết bị bếp', uid='100000000002', profile='demo-kitchen'))
    session.commit()
window = MainWindow()
window.pages['CommentPage'].show_catalog_samples()
for size in ((1440, 1000), (1024, 850), (760, 850)):
    window.resize(*size)
    window.show()
    app.processEvents()
    for index, name in ((0, 'dashboard'), (1, 'accounts'), (3, 'posts'), (4, 'comment'), (8, 'reports')):
        window.sidebar.setCurrentRow(index)
        app.processEvents()
        window.grab().save(f'tmp/ui-review/refresh-{name}-{size[0]}.png')
        page = window.stack.currentWidget()
        print(name, size[0], 'viewport', page.viewport().width(), 'content', page.widget().width())
window.hide()
database.engine.dispose()
print('Saved UI previews with fixture accounts; no live browser or API calls.')
