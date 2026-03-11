import tkinter as tk
from tkinter import messagebox, simpledialog, scrolledtext
import socket
import threading
import json
import queue

BOARD_SIZE, CELL_SIZE = 15, 40
BOARD_DIM = BOARD_SIZE * CELL_SIZE

class NetworkClient:
    def __init__(self, msg_queue):
        self.socket, self.msg_queue, self.is_connected = None, msg_queue, False

    def connect(self, host, port):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((host, port))
            self.is_connected = True
            threading.Thread(target=self.receive_messages, daemon=True).start()
            return True
        except Exception as e:
            messagebox.showerror("Connection Error", f"Failed to connect: {e}")
            return False

    def receive_messages(self):
        buffer = ""
        while self.is_connected:
            try:
                data = self.socket.recv(4096).decode('utf-8')
                if not data: break
                buffer += data
                while '\n' in buffer:
                    msg_str, buffer = buffer.split('\n', 1)
                    if msg_str: self.msg_queue.put(json.loads(msg_str))
            except (ConnectionResetError, OSError, json.JSONDecodeError): break
        if self.is_connected:
            self.is_connected = False
            self.msg_queue.put({'type': 'server_disconnected'})

    def send_message(self, msg):
        if self.is_connected:
            try: self.socket.sendall((json.dumps(msg) + '\n').encode('utf-8'))
            except OSError: self.close()

    def close(self):
        if self.is_connected:
            self.is_connected = False
            if self.socket:
                try: self.socket.shutdown(socket.SHUT_RDWR)
                except OSError: pass
                self.socket.close()

class GomokuGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Gomoku Game")
        self.geometry("1000x700")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.msg_queue = queue.Queue()
        self.network_client = NetworkClient(self.msg_queue)
        self.nickname, self.current_frame, self.game_state = "", None, {}
        self.reset_game_state()
        self.show_login_frame()
        self.process_messages()

    def on_closing(self):
        self.network_client.close()
        self.destroy()

    def reset_game_state(self):
        self.game_state = {"in_room": False, "is_player": False, "my_color": None, "current_turn": None, "board": None}

    def process_messages(self):
        try:
            while not self.msg_queue.empty():
                self.handle_server_message(self.msg_queue.get_nowait())
        finally:
            self.after(100, self.process_messages)
            
    def switch_frame(self, frame_class):
        if self.current_frame: self.current_frame.destroy()
        self.current_frame = frame_class(self)
        self.current_frame.pack(fill="both", expand=True)
        
    def show_login_frame(self):
        self.reset_game_state()
        self.switch_frame(LoginFrame)
        
    def show_lobby_frame(self): 
        self.reset_game_state()
        self.switch_frame(LobbyFrame)

    def show_game_frame(self): self.switch_frame(GameFrame)

    def handle_server_message(self, msg):
        msg_type = msg.get('type')
        handler = getattr(self.current_frame, f"handle_{msg_type}", None)
        if handler: handler(msg)
        elif msg_type == 'server_disconnected':
            if self.game_state['in_room']: messagebox.showinfo("Connection Lost", "Try to reconnect with the same nickname.")
            else: messagebox.showerror("Connection Lost", "Disconnected from the server.")
            self.network_client.close()
            self.show_login_frame()
        elif msg_type == 'error': messagebox.showerror("Error", msg.get('message'))

class LoginFrame(tk.Frame):
    def __init__(self, master):
        super().__init__(master)
        tk.Label(self, text="Gomoku", font=("Arial", 30)).pack(pady=40)
        tk.Label(self, text="Enter Nickname:", font=("Arial", 14)).pack(pady=10)
        self.nick_entry = tk.Entry(self, font=("Arial", 14), width=20)
        self.nick_entry.pack(pady=5)
        self.nick_entry.insert(0, self.master.nickname)
        tk.Label(self, text="Server IP:", font=("Arial", 14)).pack(pady=10)
        self.ip_entry = tk.Entry(self, font=("Arial", 14), width=20)
        self.ip_entry.insert(0, "127.0.0.1")
        self.ip_entry.pack(pady=5)
        tk.Button(self, text="Connect", font=("Arial", 14), command=self.connect).pack(pady=20)

    def connect(self):
        nick, ip = self.nick_entry.get().strip(), self.ip_entry.get().strip()
        if not nick or not ip: messagebox.showwarning("Input Error", "Nickname and IP cannot be empty.")
        elif self.master.network_client.connect(ip, 8888):
            self.master.nickname = nick
            self.master.network_client.send_message({'type': 'login', 'nickname': nick})

    def handle_login_success(self, msg):
        messagebox.showinfo("Success", "Successfully logged in!")
        self.master.show_lobby_frame()

    def handle_login_fail(self, msg):
        messagebox.showerror("Login Failed", msg.get('reason'))
        self.master.network_client.close()
    
    def handle_reconnect_success(self, msg):
        messagebox.showinfo("Success", "Reconnected to your game successfully!")
        self.master.game_state.update(in_room=True, is_player=True, my_color=msg['color'], board=msg['board'], current_turn=msg['turn'], opponent=msg['opponent'])
        self.master.show_game_frame()
        self.master.current_frame.handle_chat_history(msg)

class LobbyFrame(tk.Frame):
    def __init__(self, master):
        super().__init__(master)
        tk.Label(self, text=f"Welcome, {self.master.nickname}! - Lobby", font=("Arial", 20)).pack(pady=20)
        room_frame = tk.Frame(self); room_frame.pack(pady=10, padx=20, fill="both", expand=True)
        self.listbox = tk.Listbox(room_frame, font=("Arial", 12)); self.listbox.pack(side="left", fill="both", expand=True)
        scroll = tk.Scrollbar(room_frame, command=self.listbox.yview); scroll.pack(side="right", fill="y")
        self.listbox.config(yscrollcommand=scroll.set)
        btn_frame = tk.Frame(self); btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="Create Room", command=self.create_room).pack(side="left", padx=10)
        tk.Button(btn_frame, text="Join Room", command=self.join_room).pack(side="left", padx=10)
        tk.Button(btn_frame, text="Spectate Room", command=self.spectate_room).pack(side="left", padx=10)
        tk.Button(btn_frame, text="Refresh List", command=self.refresh).pack(side="left", padx=10)
        self.refresh()

    def refresh(self): self.master.network_client.send_message({'type': 'list_rooms'})
    
    def create_room(self):
        if (name := simpledialog.askstring("Create Room", "Enter room name:")):
            self.master.network_client.send_message({'type': 'create_room', 'room_name': name})

    def get_selected(self):
        if not self.listbox.curselection():
            messagebox.showwarning("Selection Error", "Please select a room.")
            return None
        return self.listbox.get(self.listbox.curselection()[0]).split(' ')[0]

    def join_room(self):
        if (name := self.get_selected()): self.master.network_client.send_message({'type': 'join_room', 'room_name': name})

    def spectate_room(self):
        if (name := self.get_selected()): self.master.network_client.send_message({'type': 'spectate_room', 'room_name': name})

    def handle_room_list(self, msg):
        self.listbox.delete(0, tk.END)
        for room in msg['rooms']:
            self.listbox.insert(tk.END, f"{room['name']} ({len(room['players'])}/2) - {room['status']} | Players: {', '.join(room['players'])}")

    def handle_join_success(self, msg):
        self.master.game_state.update(in_room=True, is_player=True, my_color=msg['color'])
        self.master.show_game_frame()
        messagebox.showinfo("Joined Room", f"You joined '{msg['room_name']}' as player {msg['color']}.")

    def handle_spectate_success(self, msg):
        self.master.game_state.update(in_room=True, is_player=False, board=msg['board'], current_turn=msg['turn'])
        self.master.show_game_frame()
        self.master.current_frame.handle_chat_history(msg)
        messagebox.showinfo("Spectating", f"You are now spectating '{msg['room_name']}'.")

class GameFrame(tk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.gs, self.timer_job = self.master.game_state, None
        
        main = tk.Frame(self); main.pack(fill="both", expand=True, padx=20, pady=20)
        board_area = tk.Frame(main); board_area.pack(side="left", fill="both", expand=True)
        self.status = tk.Label(board_area, text="Waiting...", font=("Arial", 16)); self.status.pack(pady=10)
        self.timer = tk.Label(board_area, text="", font=("Arial", 14), fg="darkblue"); self.timer.pack(pady=5)
        self.canvas = tk.Canvas(board_area, width=BOARD_DIM, height=BOARD_DIM, bg='#D2B48C'); self.canvas.pack()
        self.canvas.bind("<Button-1>", self.on_board_click)
        
        side_area = tk.Frame(main, width=350); side_area.pack(side="right", fill="y", padx=20); side_area.pack_propagate(False)
        tk.Label(side_area, text=f"Player: {self.master.nickname}", font=("Arial", 14)).pack(pady=5, anchor='w')
        role = "Player" if self.gs['is_player'] else "Spectator"; color = f" ({self.gs['my_color']})" if self.gs.get('my_color') else ""
        tk.Label(side_area, text=f"Role: {role}{color}", font=("Arial", 14)).pack(pady=5, anchor='w')
        tk.Label(side_area, text="Chat", font=("Arial", 16)).pack(pady=10)
        self.chat_box = scrolledtext.ScrolledText(side_area, state='disabled', wrap=tk.WORD, font=("Arial", 10)); self.chat_box.pack(fill="both", expand=True)
        self.chat_input = tk.Entry(side_area, font=("Arial", 12)); self.chat_input.pack(fill="x", pady=5); self.chat_input.bind("<Return>", self.send_chat)
        self.draw_board()
        self.update_status_label()

    def draw_board(self):
        self.canvas.delete("all")
        for i in range(BOARD_SIZE):
            self.canvas.create_line(CELL_SIZE//2, i*CELL_SIZE+CELL_SIZE//2, BOARD_DIM-CELL_SIZE//2, i*CELL_SIZE+CELL_SIZE//2)
            self.canvas.create_line(i*CELL_SIZE+CELL_SIZE//2, CELL_SIZE//2, i*CELL_SIZE+CELL_SIZE//2, BOARD_DIM-CELL_SIZE//2)
        if self.gs.get('board'):
            for r, row in enumerate(self.gs['board']):
                for c, color in enumerate(row):
                    if color: self.draw_stone(r, c, color)

    def draw_stone(self, r, c, color):
        x0, y0, x1, y1 = c*CELL_SIZE+5, r*CELL_SIZE+5, (c+1)*CELL_SIZE-5, (r+1)*CELL_SIZE-5
        self.canvas.create_oval(x0, y0, x1, y1, fill=color, outline=color)

    def on_board_click(self, e):
        if self.gs['is_player'] and self.gs['my_color'] == self.gs['current_turn']:
            self.master.network_client.send_message({'type': 'place_stone', 'row': e.y//CELL_SIZE, 'col': e.x//CELL_SIZE})
        
    def send_chat(self, e=None):
        if (msg := self.chat_input.get()):
            self.master.network_client.send_message({'type': 'chat_message', 'message': msg})
            self.chat_input.delete(0, tk.END)

    def update_chat_display(self, text, tag=None):
        self.chat_box.config(state='normal')
        self.chat_box.tag_config("spectator", foreground="gray")
        self.chat_box.tag_config("system", foreground="green", font=("Arial", 10, "italic"))
        self.chat_box.insert(tk.END, text + '\n', tag)
        self.chat_box.config(state='disabled'); self.chat_box.yview(tk.END)

    def start_countdown(self, time_limit):
        if self.timer_job: self.after_cancel(self.timer_job)
        self.remaining_time = time_limit
        self.update_timer()

    def update_timer(self):
        if self.remaining_time > 0 and self.gs['current_turn']:
            self.timer.config(text=f"Time remaining: {self.remaining_time}s")
            self.remaining_time -= 1
            self.timer_job = self.after(1000, self.update_timer)
        else: self.timer.config(text="")

    def handle_game_start(self, msg):
        self.gs.update(board=msg['board'], current_turn=msg['turn'], opponent=msg['opponent'])
        self.update_chat_display(f"--- Game started! Opponent: {self.gs['opponent']} ---", "system")
        self.draw_board(); self.update_status_label()

    def handle_update_board(self, msg):
        if not self.gs.get('board'): self.gs['board'] = [['' for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
        self.gs['board'][msg['row']][msg['col']] = msg['color']
        self.draw_stone(msg['row'], msg['col'], msg['color'])
    
    def handle_update_turn(self, msg):
        self.gs['current_turn'] = msg['turn']
        self.update_status_label(); self.start_countdown(msg.get('time_limit', 0))

    def handle_chat_update(self, msg):
        tag = "spectator" if msg.get('is_spectator') else None
        prefix = "[Spectator] " if msg.get('is_spectator') else ""
        self.update_chat_display(f"{prefix}{msg['sender']}: {msg['message']}", tag)
        
    def handle_chat_history(self, msg):
        self.gs.update(board=msg.get('board'))
        self.draw_board()
        for chat in msg.get('chat_history', []): self.update_chat_display(chat)
        self.update_status_label()

    def handle_game_over(self, msg):
        self.gs['current_turn'] = None; self.start_countdown(0)
        winner, reason = msg.get('winner'), msg.get('reason')
        text = f"Player {winner} has won the game!"
        if reason == 'opponent_left': text = "Your opponent left. You win!"
        elif self.gs['is_player'] and winner == self.gs['my_color']:
            text = "Congratulations, you won!" if reason == 'win' else "You won by timeout!"
        
        messagebox.showinfo("Game Over", text)
        self.status.config(text="Game Over!")
        self.canvas.unbind("<Button-1>")
        self.after(2000, self.master.show_lobby_frame)
    
    def handle_opponent_disconnected(self, msg):
        self.update_chat_display(f"--- Player '{msg['nickname']}' disconnected. Waiting... ---", "system")
        self.status.config(text="Opponent disconnected", fg="orange"); self.start_countdown(0)

    def handle_opponent_reconnected(self, msg):
        self.update_chat_display(f"--- Player '{msg['nickname']}' reconnected! ---", "system")
        self.update_status_label()

    def update_status_label(self):
        turn = self.gs.get('current_turn')
        if turn:
            text, color = (("Your turn", "blue") if self.gs['is_player'] and turn == self.gs['my_color'] 
                           else (f"{turn.capitalize()}'s turn", "red"))
            self.status.config(text=text, fg=color)
        elif self.gs.get('in_room') and not self.gs.get('opponent'):
            self.status.config(text="Waiting for opponent...", fg="black")

if __name__ == "__main__":
    GomokuGUI().mainloop()
