from types import SimpleNamespace

from telegram.ext import CallbackQueryHandler

from clone_manager.message_editor.handlers import add_editor_handlers


def test_editor_handler_registration_includes_callback_handlers():
    app = SimpleNamespace(handlers=[])
    app.add_handler = lambda handler, group=0: app.handlers.append((handler, group))

    add_editor_handlers(app)

    callback_handlers = [
        handler for handler, _group in app.handlers
        if isinstance(handler, CallbackQueryHandler)
    ]
    assert len(callback_handlers) == 2
    assert len(app.handlers) == 5
