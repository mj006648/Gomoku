BOARD_SIZE = 15

class GomokuGame:
    def __init__(self):
        self.board = [['' for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
        self.current_turn = 'black'
        self.winner = None

    def place_stone(self, row, col, color):
        if 0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE and self.board[row][col] == '':
            self.board[row][col] = color
            return True
        return False

    def switch_turn(self):
        self.current_turn = 'white' if self.current_turn == 'black' else 'black'

    def check_win(self, row, col):
        color = self.board[row][col]
        if not color: return False
        directions = [(0, 1), (1, 0), (1, 1), (1, -1)]
        for dr, dc in directions:
            count = 1
            for i in range(1, 5):
                r, c = row + dr * i, col + dc * i
                if 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and self.board[r][c] == color:
                    count += 1
                else: break
            for i in range(1, 5):
                r, c = row - dr * i, col - dc * i
                if 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and self.board[r][c] == color:
                    count += 1
                else: break
            if count >= 5:
                self.winner = color
                return True
        return False
        
    def reset_game(self):
        self.board = [['' for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
        self.current_turn = 'black'
        self.winner = None
