"""Authored native pixels for the approved steel-console concept.

All coordinates are game pixels, not resampled concept art. Four flat indices
share the reserved HUD palette: background, steel, ivory, teal. This module is
also used by the offline asset compiler; it has no configuration dependencies.
"""

PALETTE = [(16, 24, 32), (102, 119, 122), (238, 230, 197), (82, 132, 132)]

HEALTH_FONT = {
    '0': ('011110','110011','110011','110011','110011','110011','110011','110011','110011','011110'),
    '1': ('001100','011100','111100','001100','001100','001100','001100','001100','001100','111111'),
    '2': ('011110','110011','000011','000011','000110','001100','011000','110000','110000','111111'),
    '3': ('111110','000011','000011','000011','011110','000011','000011','000011','000011','111110'),
    '4': ('000110','001110','011110','110110','110110','110110','111111','000110','000110','000110'),
    '5': ('111111','110000','110000','110000','111110','000011','000011','000011','110011','011110'),
    '6': ('001110','011000','110000','110000','111110','110011','110011','110011','110011','011110'),
    '7': ('111111','000011','000011','000110','000110','001100','001100','011000','011000','011000'),
    '8': ('011110','110011','110011','110011','011110','110011','110011','110011','110011','011110'),
    '9': ('011110','110011','110011','110011','110011','011111','000011','000011','000110','011100'),
}


def paint(target, rows, x, y, *, ink=None):
    for dy, row in enumerate(rows):
        for dx, value in enumerate(row):
            if value != '0':
                target[y + dy][x + dx] = int(value) if ink is None else ink


def panel_pixels():
    """One connected chassis; dynamic patches preserve its framing pixels."""
    p = [[0] * 160 for _ in range(24)]
    p[0] = [1] * 160                 # uninterrupted world/HUD divider
    p[1] = [1] * 160
    for x in range(3, 157):
        p[2][x] = p[21][x] = p[22][x] = 1
    for y in range(4, 20):
        p[y][1] = p[y][2] = p[y][157] = p[y][158] = 1
    for x, y in ((2, 3), (157, 3), (2, 20), (157, 20)):
        p[y][x] = 1
    for x in (4, 5, 154, 155):
        p[1][x] = 2
    # The portrait shares the upper/lower chassis rails. Narrow uprights
    # define its recess without increasing the sixteen-pixel portrait.
    for y in range(3, 21):
        p[y][68] = p[y][69] = p[y][90] = p[y][91] = 1
    for y in range(5, 19):
        p[y][123] = 1
    for x in (8, 12, 16):
        p[21][x] = 0
    for x in (62, 96):
        p[5][x] = p[18][x] = 1
    paint(p, ('00022000','00022000','00022000','22222222',
              '22222222','00022000','00022000','00011000'), 7, 8)
    # Remaining hostiles: ivory skull with paired eye sockets, nasal cavity
    # and separated teeth. It stays inside the icon's own eight-pixel tile.
    paint(p, ('00222200','02222220','22222222','20022002','20022002',
              '22200222','01222210','00222200','00202000'), 104, 7)
    return p


def portrait_pixels():
    """Armoured brow and respirator from the approved whole-HUD concept.

    Keep the face covered: the narrow eye recess and cheek plates sit above
    a rigid central filter. Each cel retains the same armour silhouette and
    crown reflection, including blink/death; no cel becomes a flat badge.
    """
    rows = (
        '0000111111110000',
        '0001333322331000',
        '0013333322333100',
        '0133333333333310',
        '0131111111111310',
        '1100000110000011',
        '1310000110000131',
        '1312220110222131',
        '0131111331111310',
        '0133113333113310',
        '0013113003113100',
        '0011113113111100',
        '0001313003131000',
        '0001313113131000',
        '0000111331110000',
        '0000011111100000',
    )
    assert len(rows) == 16 and all(len(row) == 16 for row in rows)
    p = [[int(value) for value in row] for row in rows]
    cels = [[row[:] for row in p] for _ in range(4)]
    # Closed/squinting eyes stay inside the recess, above the respirator.
    for x in (3, 4, 5, 10, 11, 12):
        cels[1][7][x] = 0
        cels[3][6][x] = cels[3][7][x] = 0
    for x in (3, 4, 5): cels[2][7][x] = 0
    cels[2][8][3] = 1
    cels[2][9][3] = 0
    # A dark diagonal break distinguishes the terminal cel from a blink.
    cels[3][2][5] = cels[3][3][6] = cels[3][4][7] = 0
    return cels
