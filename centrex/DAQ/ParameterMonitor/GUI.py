import tkinter

root = tkinter.Tk()

cont1 = tkinter.Frame(root)
cont1.pack()

button1 = tkinter.Button(cont1, text="Hello, World!", background = "green")
button1.pack(fill='y')

button2 = tkinter.Button(cont1, text="Hello, World!", background = "green")
button2.pack(fill='y')

def button1Click(event):
    if button1["background"] == "green": ### (4)
        button1["background"] = "yellow"
    else:
        button1["background"] = "green"

def button2Click(event):
    root.destroy()

button1.bind("<Button-1>", button1Click)
button1.bind("<Return>", button1Click)

button2.bind("<Button-1>", button2Click)
button2.bind("<Return>", button2Click)

root.mainloop()
