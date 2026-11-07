"""Windows DPAPI, bound to current user; no credentials in source or logs."""
import ctypes
import json
from ctypes import wintypes

class Blob(ctypes.Structure):
    _fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_byte))]

def crypt(data,decrypt=False):
    buffer=ctypes.create_string_buffer(data)
    source=Blob(len(data),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_byte)))
    result=Blob()
    fn=ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if not fn(ctypes.byref(source),None,None,None,None,1,ctypes.byref(result)):
        raise OSError('Windows secret protection failed')
    try:return ctypes.string_at(result.data,result.size)
    finally:ctypes.windll.kernel32.LocalFree(result.data)

def load_secrets(path):
    if not path.exists():return {}
    return json.loads(crypt(path.read_bytes(),True).decode())

def setup(path):
    import tkinter as tk
    from tkinter import messagebox
    import os
    from watcher import send_telegram
    root=tk.Tk();root.title('Local price watcher — Telegram setup')
    tk.Label(root,text='Enter the same Telegram bot token and chat ID.\nStored encrypted for your Windows account only.').pack(padx=20,pady=15)
    tk.Label(root,text='Bot token').pack();token=tk.Entry(root,show='*',width=65);token.pack(padx=20)
    tk.Label(root,text='Chat ID').pack();chat=tk.Entry(root,width=65);chat.pack(padx=20)
    def save():
        values={'TELEGRAM_BOT_TOKEN':token.get().strip(),'TELEGRAM_CHAT_ID':chat.get().strip()}
        if not all(values.values()):messagebox.showerror('Missing values','Enter both fields.');return
        os.environ.update(values)
        try:
            if not send_telegram('اختبار المراقب المحلي — الكمبيوتر يحتاج أن يكون شغالًا ومتصلًا بالإنترنت.'):
                raise ValueError()
            path.write_bytes(crypt(json.dumps(values).encode()))
            messagebox.showinfo('Saved','Test delivered. Local Telegram is ready.');root.destroy()
        except Exception:messagebox.showerror('Not saved','Could not send test. Check the token and chat ID.')
    tk.Button(root,text='Save securely and send test',command=save).pack(pady=20)
    root.mainloop()

if __name__=='__main__':
    from pathlib import Path
    setup(Path(__file__).resolve().parent/'local-secrets.bin')
