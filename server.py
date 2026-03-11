import socket
import threading
import json
from game_logic import GomokuGame

TURN_TIME_LIMIT = 30
RECONNECT_GRACE_PERIOD = 60

class GameRoom:
    def __init__(self, name, server):
        self.name = name
        self.server = server
        self.players = {}
        self.spectators = []
        self.game = GomokuGame()
        self.chat_history = []
        self.lock = threading.RLock() 
        self.turn_timer = None
        self.reconnect_timers = {}

    def broadcast(self, message, exclude_client=None):
        with self.lock:
            targets = [p['thread'] for p in self.players.values() if p.get('thread')] + self.spectators
            for client in targets:
                if client != exclude_client:
                    client.send_message(message)

    def add_player(self, player_thread):
        with self.lock:
            if len(self.players) >= 2 and player_thread.nickname not in self.players: return None
            color = 'black' if not any(p['color'] == 'black' for p in self.players.values()) else 'white'
            self.players[player_thread.nickname] = {'color': color, 'thread': player_thread}
            return color

    def add_spectator(self, spectator_thread):
        with self.lock:
            self.spectators.append(spectator_thread)

    def handle_place_stone(self, nickname, message):
        with self.lock:
            if self.game.winner or nickname not in self.players: return
            player_color = self.players[nickname]['color']
            if player_color == self.game.current_turn:
                row, col = message.get('row'), message.get('col')
                if self.game.place_stone(row, col, player_color):
                    self.cancel_turn_timer()
                    self.broadcast({'type': 'update_board', 'row': row, 'col': col, 'color': player_color})
                    if self.game.check_win(row, col):
                        self.broadcast({'type': 'game_over', 'winner': player_color, 'reason': 'win'})
                        self.end_game_and_cleanup()
                    else:
                        self.game.switch_turn()
                        self.start_turn_timer()

    def handle_chat_message(self, nickname, message):
        with self.lock:
            chat_msg = message.get('message')
            is_spectator = nickname not in self.players
            if not is_spectator: self.chat_history.append(f"{nickname}: {chat_msg}")
        self.broadcast({'type': 'chat_update', 'sender': nickname, 'message': chat_msg, 'is_spectator': is_spectator})

    def start_turn_timer(self):
        with self.lock:
            self.cancel_turn_timer()
            current_player_nick = self.get_player_by_color(self.game.current_turn)
            if current_player_nick:
                self.turn_timer = threading.Timer(TURN_TIME_LIMIT, self.on_timeout, args=[current_player_nick])
                self.turn_timer.start()
                self.broadcast({'type': 'update_turn', 'turn': self.game.current_turn, 'time_limit': TURN_TIME_LIMIT})

    def cancel_turn_timer(self):
        if self.turn_timer:
            self.turn_timer.cancel()
            self.turn_timer = None

    def on_timeout(self, timed_out_player):
        with self.lock:
            if self.game.winner or timed_out_player not in self.players: return
            winner_color = 'white' if self.players[timed_out_player]['color'] == 'black' else 'black'
            self.game.winner = winner_color
        self.broadcast({'type': 'game_over', 'winner': winner_color, 'reason': 'timeout'})
        self.end_game_and_cleanup()

    def handle_disconnection(self, disconnected_thread):
        nickname = disconnected_thread.nickname
        with self.lock:
            is_player = nickname in self.players
            if is_player:
                self.players[nickname]['thread'] = None
            elif disconnected_thread in self.spectators:
                self.spectators.remove(disconnected_thread)
        if is_player:
            self.broadcast({'type': 'opponent_disconnected', 'nickname': nickname})
            self.cancel_turn_timer()
            self.reconnect_timers[nickname] = threading.Timer(RECONNECT_GRACE_PERIOD, self.on_reconnect_fail, args=[nickname])
            self.reconnect_timers[nickname].start()

    def on_reconnect_fail(self, nickname):
        winner_color = None
        with self.lock:
            if not self.players.get(nickname) or self.players[nickname].get('thread') is not None: return
            opponent = self.get_opponent_nickname(nickname)
            del self.players[nickname]
            if opponent and self.players.get(opponent):
                self.game.winner = self.players[opponent]['color']
                winner_color = self.game.winner
        if winner_color:
            self.broadcast({'type': 'game_over', 'winner': winner_color, 'reason': 'opponent_left'})
            self.end_game_and_cleanup()
        else:
            with self.lock: self.cleanup_room()

    def handle_reconnection(self, player_thread):
        nickname = player_thread.nickname
        with self.lock:
            self.players[nickname]['thread'] = player_thread
            if nickname in self.reconnect_timers: self.reconnect_timers.pop(nickname).cancel()
        self.broadcast({'type': 'opponent_reconnected', 'nickname': nickname}, exclude_client=player_thread)
        with self.lock:
            if not self.game.winner and len([p for p in self.players.values() if p['thread']]) == 2:
                self.start_turn_timer()
    
    def end_game_and_cleanup(self):
        with self.lock:
            self.cancel_turn_timer()
            all_threads = [p['thread'] for p in self.players.values() if p.get('thread')] + self.spectators
            for thread in all_threads:
                thread.room = None
            self.cleanup_room()

    def cleanup_room(self):
        if self.name in self.server.rooms:
            del self.server.rooms[self.name]
            print(f"[INFO] Room '{self.name}' closed.")
            self.server.broadcast_room_list()
            
    def get_opponent_nickname(self, nickname):
        for p_nick in self.players:
            if p_nick != nickname: return p_nick
        return None

    def get_player_by_color(self, color):
        for nick, info in self.players.items():
            if info['color'] == color: return nick
        return None

class ClientThread(threading.Thread):
    def __init__(self, socket, addr, server):
        super().__init__()
        self.socket, self.addr, self.server = socket, addr, server
        self.nickname, self.room = None, None

    def run(self):
        buffer = ""
        try:
            while True:
                data = self.socket.recv(4096).decode('utf-8')
                if not data: break
                buffer += data
                while '\n' in buffer:
                    msg_str, buffer = buffer.split('\n', 1)
                    if msg_str: self.handle_message(json.loads(msg_str))
        except (ConnectionResetError, json.JSONDecodeError, OSError): pass
        finally:
            print(f"[INFO] Connection lost with {self.addr}")
            self.cleanup()

    def handle_message(self, msg):
        msg_type = msg.get('type')
        if not self.nickname and msg_type != 'login': return

        if msg_type == 'login': self.handle_login(msg)
        elif msg_type == 'list_rooms': self.send_message({'type': 'room_list', 'rooms': self.server.get_rooms_info()})
        elif msg_type == 'create_room': self.handle_create_room(msg)
        elif msg_type == 'join_room': self.handle_join_room(msg)
        elif msg_type == 'spectate_room': self.handle_spectate_room(msg)
        elif self.room:
            if msg_type == 'place_stone': self.room.handle_place_stone(self.nickname, msg)
            elif msg_type == 'chat_message': self.room.handle_chat_message(self.nickname, msg)

    def handle_login(self, msg):
        nickname = msg.get('nickname')
        if self.server.is_player_disconnected(nickname):
            self.nickname, self.room = nickname, self.server.find_room_by_player(nickname)
            self.server.clients[nickname] = self
            self.room.handle_reconnection(self)
            self.send_message({'type': 'reconnect_success', 'room_name': self.room.name, 'color': self.room.players[nickname]['color'], 'board': self.room.game.board, 'turn': self.room.game.current_turn, 'opponent': self.room.get_opponent_nickname(nickname), 'chat_history': self.room.chat_history})
        elif self.server.is_nickname_taken(nickname):
            self.send_message({'type': 'login_fail', 'reason': 'Nickname is already taken.'})
        else:
            self.nickname = nickname
            self.server.clients[nickname] = self
            self.send_message({'type': 'login_success'})
            print(f"[INFO] User '{nickname}' logged in.")

    def handle_create_room(self, msg):
        room_name = msg.get('room_name')
        if room_name in self.server.rooms:
            self.send_message({'type': 'error', 'message': 'Room exists.'})
        else:
            self.room = GameRoom(room_name, self.server)
            self.server.rooms[room_name] = self.room
            color = self.room.add_player(self)
            self.send_message({'type': 'join_success', 'room_name': room_name, 'color': color})
            print(f"[INFO] Room '{room_name}' created by '{self.nickname}'.")
            self.server.broadcast_room_list()
            
    def handle_join_room(self, msg):
        room_name = msg.get('room_name')
        room = self.server.rooms.get(room_name)
        if room:
            color = room.add_player(self)
            if color:
                self.room = room
                self.send_message({'type': 'join_success', 'room_name': room.name, 'color': color})
                with room.lock:
                    opponent = room.get_opponent_nickname(self.nickname)
                    start_msg = {'type': 'game_start', 'board': room.game.board, 'turn': room.game.current_turn}
                    room.players[opponent]['thread'].send_message({**start_msg, 'opponent': self.nickname})
                    self.send_message({**start_msg, 'opponent': opponent})
                print(f"[INFO] '{self.nickname}' joined '{room.name}'. Game started.")
                room.start_turn_timer()
                self.server.broadcast_room_list()
            else: self.send_message({'type': 'error', 'message': 'Room full.'})
        else: self.send_message({'type': 'error', 'message': 'Room missing.'})

    def handle_spectate_room(self, msg):
        room = self.server.rooms.get(msg.get('room_name'))
        if room:
            self.room = room
            room.add_spectator(self)
            self.send_message({'type': 'spectate_success', 'room_name': room.name, 'board': room.game.board, 'turn': room.game.current_turn, 'chat_history': room.chat_history})
            print(f"[INFO] '{self.nickname}' started spectating '{room.name}'.")
        else: self.send_message({'type': 'error', 'message': 'Room missing.'})

    def send_message(self, msg):
        try: self.socket.sendall((json.dumps(msg) + '\n').encode('utf-8'))
        except (OSError, ConnectionAbortedError): pass
            
    def cleanup(self):
        if self.room: self.room.handle_disconnection(self)
        if self.nickname and self.nickname in self.server.clients:
            del self.server.clients[self.nickname]
        self.socket.close()

class GomokuServer:
    def __init__(self, host, port):
        self.host, self.port = host, port
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.clients, self.rooms, self.lock = {}, {}, threading.RLock()

    def start(self):
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen()
        print(f"[INFO] Server listening on {self.host}:{self.port}")
        try:
            while True:
                sock, addr = self.server_socket.accept()
                print(f"[INFO] Accepted connection from {addr}")
                ClientThread(sock, addr, self).start()
        except KeyboardInterrupt: print("\n[INFO] Server is shutting down.")
        finally: self.server_socket.close()
    
    def is_nickname_taken(self, nick):
        with self.lock: return nick in self.clients
    
    def is_player_disconnected(self, nick):
        with self.lock:
            room = self.find_room_by_player(nick)
            return room and room.players.get(nick, {}).get('thread') is None
        
    def find_room_by_player(self, nick):
        for room in self.rooms.values():
            if nick in room.players: return room
        return None

    def get_rooms_info(self):
        with self.lock:
            return [{'name': name, 'status': "In Progress" if len(r.players) == 2 else "Waiting", 'players': list(r.players.keys())} for name, r in self.rooms.items()]

    def broadcast_room_list(self):
        rooms_info = self.get_rooms_info()
        with self.lock:
            for client in list(self.clients.values()):
                if client.room is None: client.send_message({'type': 'room_list', 'rooms': rooms_info})

if __name__ == "__main__":
    GomokuServer("0.0.0.0", 8888).start()
