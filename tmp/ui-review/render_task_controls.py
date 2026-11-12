"""Preview active/paused controls using fixture state, without starting any tasks."""
import runpy
namespace = runpy.run_path('tmp/ui-review/render_refresh.py')
window, app = namespace['window'], namespace['app']
window.resize(1440, 1000)
window.show()
window.sidebar.setCurrentRow(4)
page = window.pages['CommentPage']
page._set_scanning(True)
page.toggle_scan_pause()
app.processEvents()
window.grab().save('tmp/ui-review/task-paused-comment.png')
page._set_scanning(False)
page._scan_control.stop()
window.sidebar.setCurrentRow(3)
posts = window.pages['PostPage']
posts._publish_pending = {'fixture'}
posts.pause_publish_button.setEnabled(True)
posts.stop_publish_button.setEnabled(True)
posts.toggle_publish_pause()
app.processEvents()
window.grab().save('tmp/ui-review/task-paused-posts.png')
posts._publish_pending.clear()
posts._publish_control.stop()
window.hide()
namespace['database'].engine.dispose()
print('Rendered paused states without browser or AI calls.')
