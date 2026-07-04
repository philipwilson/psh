# Appendix D: ASCII Character Set

This appendix provides a comprehensive ASCII character reference table, useful for understanding character codes, escape sequences, and text processing in PSH.

## Table of Contents

1. [ASCII Control Characters (0-31)](#ascii-control-characters-0-31)
2. [ASCII Printable Characters (32-127)](#ascii-printable-characters-32-127)
3. [Extended ASCII (128-255)](#extended-ascii-128-255)
4. [Using ASCII in PSH](#using-ascii-in-psh)
5. [Escape Sequences](#escape-sequences)
6. [Character Conversions](#character-conversions)
7. [Practical Examples](#practical-examples)

## ASCII Control Characters (0-31)

Control characters are non-printing characters that control how text is processed.

| Dec | Hex | Oct | Char | Abbr | Name | Description | Keyboard |
|-----|-----|-----|------|------|------|-------------|----------|
| 0 | 00 | 000 | ^@ | NUL | Null | Null character | Ctrl+@ |
| 1 | 01 | 001 | ^A | SOH | Start of Heading | Start of header | Ctrl+A |
| 2 | 02 | 002 | ^B | STX | Start of Text | Start of text | Ctrl+B |
| 3 | 03 | 003 | ^C | ETX | End of Text | End of text, interrupt | Ctrl+C |
| 4 | 04 | 004 | ^D | EOT | End of Transmission | End of file (EOF) | Ctrl+D |
| 5 | 05 | 005 | ^E | ENQ | Enquiry | Enquiry | Ctrl+E |
| 6 | 06 | 006 | ^F | ACK | Acknowledge | Acknowledge | Ctrl+F |
| 7 | 07 | 007 | ^G | BEL | Bell | Terminal bell | Ctrl+G |
| 8 | 08 | 010 | ^H | BS | Backspace | Backspace | Ctrl+H |
| 9 | 09 | 011 | ^I | HT | Horizontal Tab | Tab character | Ctrl+I, Tab |
| 10 | 0A | 012 | ^J | LF | Line Feed | New line (Unix) | Ctrl+J, Enter |
| 11 | 0B | 013 | ^K | VT | Vertical Tab | Vertical tab | Ctrl+K |
| 12 | 0C | 014 | ^L | FF | Form Feed | Form feed, clear screen | Ctrl+L |
| 13 | 0D | 015 | ^M | CR | Carriage Return | Carriage return | Ctrl+M |
| 14 | 0E | 016 | ^N | SO | Shift Out | Shift out | Ctrl+N |
| 15 | 0F | 017 | ^O | SI | Shift In | Shift in | Ctrl+O |
| 16 | 10 | 020 | ^P | DLE | Data Link Escape | Data link escape | Ctrl+P |
| 17 | 11 | 021 | ^Q | DC1 | Device Control 1 | XON (resume) | Ctrl+Q |
| 18 | 12 | 022 | ^R | DC2 | Device Control 2 | Device control 2 | Ctrl+R |
| 19 | 13 | 023 | ^S | DC3 | Device Control 3 | XOFF (pause) | Ctrl+S |
| 20 | 14 | 024 | ^T | DC4 | Device Control 4 | Device control 4 | Ctrl+T |
| 21 | 15 | 025 | ^U | NAK | Negative Acknowledge | Kill line | Ctrl+U |
| 22 | 16 | 026 | ^V | SYN | Synchronous Idle | Literal next | Ctrl+V |
| 23 | 17 | 027 | ^W | ETB | End of Trans Block | Delete word | Ctrl+W |
| 24 | 18 | 030 | ^X | CAN | Cancel | Cancel line | Ctrl+X |
| 25 | 19 | 031 | ^Y | EM | End of Medium | Paste (yank) | Ctrl+Y |
| 26 | 1A | 032 | ^Z | SUB | Substitute | Suspend process | Ctrl+Z |
| 27 | 1B | 033 | ^[ | ESC | Escape | Escape character | Ctrl+[, Esc |
| 28 | 1C | 034 | ^\ | FS | File Separator | Quit | Ctrl+\ |
| 29 | 1D | 035 | ^] | GS | Group Separator | Group separator | Ctrl+] |
| 30 | 1E | 036 | ^^ | RS | Record Separator | Record separator | Ctrl+^ |
| 31 | 1F | 037 | ^_ | US | Unit Separator | Undo | Ctrl+_ |

## ASCII Printable Characters (32-127)

These are the standard visible characters.

### Space and Punctuation (32-47)

| Dec | Hex | Oct | Char | Description |
|-----|-----|-----|------|-------------|
| 32 | 20 | 040 | ` ` | Space |
| 33 | 21 | 041 | `!` | Exclamation mark |
| 34 | 22 | 042 | `"` | Double quote |
| 35 | 23 | 043 | `#` | Number sign (hash) |
| 36 | 24 | 044 | `$` | Dollar sign |
| 37 | 25 | 045 | `%` | Percent sign |
| 38 | 26 | 046 | `&` | Ampersand |
| 39 | 27 | 047 | `'` | Single quote |
| 40 | 28 | 050 | `(` | Left parenthesis |
| 41 | 29 | 051 | `)` | Right parenthesis |
| 42 | 2A | 052 | `*` | Asterisk |
| 43 | 2B | 053 | `+` | Plus sign |
| 44 | 2C | 054 | `,` | Comma |
| 45 | 2D | 055 | `-` | Hyphen/minus |
| 46 | 2E | 056 | `.` | Period |
| 47 | 2F | 057 | `/` | Forward slash |

### Digits (48-57)

| Dec | Hex | Oct | Char | Description |
|-----|-----|-----|------|-------------|
| 48 | 30 | 060 | `0` | Zero |
| 49 | 31 | 061 | `1` | One |
| 50 | 32 | 062 | `2` | Two |
| 51 | 33 | 063 | `3` | Three |
| 52 | 34 | 064 | `4` | Four |
| 53 | 35 | 065 | `5` | Five |
| 54 | 36 | 066 | `6` | Six |
| 55 | 37 | 067 | `7` | Seven |
| 56 | 38 | 070 | `8` | Eight |
| 57 | 39 | 071 | `9` | Nine |

### Punctuation and Symbols (58-64)

| Dec | Hex | Oct | Char | Description |
|-----|-----|-----|------|-------------|
| 58 | 3A | 072 | `:` | Colon |
| 59 | 3B | 073 | `;` | Semicolon |
| 60 | 3C | 074 | `<` | Less than |
| 61 | 3D | 075 | `=` | Equals sign |
| 62 | 3E | 076 | `>` | Greater than |
| 63 | 3F | 077 | `?` | Question mark |
| 64 | 40 | 100 | `@` | At sign |

### Uppercase Letters (65-90)

| Dec | Hex | Oct | Char | Description |
|-----|-----|-----|------|-------------|
| 65 | 41 | 101 | `A` | Uppercase A |
| 66 | 42 | 102 | `B` | Uppercase B |
| 67 | 43 | 103 | `C` | Uppercase C |
| 68 | 44 | 104 | `D` | Uppercase D |
| 69 | 45 | 105 | `E` | Uppercase E |
| 70 | 46 | 106 | `F` | Uppercase F |
| 71 | 47 | 107 | `G` | Uppercase G |
| 72 | 48 | 110 | `H` | Uppercase H |
| 73 | 49 | 111 | `I` | Uppercase I |
| 74 | 4A | 112 | `J` | Uppercase J |
| 75 | 4B | 113 | `K` | Uppercase K |
| 76 | 4C | 114 | `L` | Uppercase L |
| 77 | 4D | 115 | `M` | Uppercase M |
| 78 | 4E | 116 | `N` | Uppercase N |
| 79 | 4F | 117 | `O` | Uppercase O |
| 80 | 50 | 120 | `P` | Uppercase P |
| 81 | 51 | 121 | `Q` | Uppercase Q |
| 82 | 52 | 122 | `R` | Uppercase R |
| 83 | 53 | 123 | `S` | Uppercase S |
| 84 | 54 | 124 | `T` | Uppercase T |
| 85 | 55 | 125 | `U` | Uppercase U |
| 86 | 56 | 126 | `V` | Uppercase V |
| 87 | 57 | 127 | `W` | Uppercase W |
| 88 | 58 | 130 | `X` | Uppercase X |
| 89 | 59 | 131 | `Y` | Uppercase Y |
| 90 | 5A | 132 | `Z` | Uppercase Z |

### Punctuation and Symbols (91-96)

| Dec | Hex | Oct | Char | Description |
|-----|-----|-----|------|-------------|
| 91 | 5B | 133 | `[` | Left square bracket |
| 92 | 5C | 134 | `\` | Backslash |
| 93 | 5D | 135 | `]` | Right square bracket |
| 94 | 5E | 136 | `^` | Caret |
| 95 | 5F | 137 | `_` | Underscore |
| 96 | 60 | 140 | `` ` `` | Backtick (grave accent) |

### Lowercase Letters (97-122)

| Dec | Hex | Oct | Char | Description |
|-----|-----|-----|------|-------------|
| 97 | 61 | 141 | `a` | Lowercase a |
| 98 | 62 | 142 | `b` | Lowercase b |
| 99 | 63 | 143 | `c` | Lowercase c |
| 100 | 64 | 144 | `d` | Lowercase d |
| 101 | 65 | 145 | `e` | Lowercase e |
| 102 | 66 | 146 | `f` | Lowercase f |
| 103 | 67 | 147 | `g` | Lowercase g |
| 104 | 68 | 150 | `h` | Lowercase h |
| 105 | 69 | 151 | `i` | Lowercase i |
| 106 | 6A | 152 | `j` | Lowercase j |
| 107 | 6B | 153 | `k` | Lowercase k |
| 108 | 6C | 154 | `l` | Lowercase l |
| 109 | 6D | 155 | `m` | Lowercase m |
| 110 | 6E | 156 | `n` | Lowercase n |
| 111 | 6F | 157 | `o` | Lowercase o |
| 112 | 70 | 160 | `p` | Lowercase p |
| 113 | 71 | 161 | `q` | Lowercase q |
| 114 | 72 | 162 | `r` | Lowercase r |
| 115 | 73 | 163 | `s` | Lowercase s |
| 116 | 74 | 164 | `t` | Lowercase t |
| 117 | 75 | 165 | `u` | Lowercase u |
| 118 | 76 | 166 | `v` | Lowercase v |
| 119 | 77 | 167 | `w` | Lowercase w |
| 120 | 78 | 170 | `x` | Lowercase x |
| 121 | 79 | 171 | `y` | Lowercase y |
| 122 | 7A | 172 | `z` | Lowercase z |

### Final Punctuation (123-127)

| Dec | Hex | Oct | Char | Description |
|-----|-----|-----|------|-------------|
| 123 | 7B | 173 | `{` | Left curly brace |
| 124 | 7C | 174 | `|` | Vertical bar (pipe) |
| 125 | 7D | 175 | `}` | Right curly brace |
| 126 | 7E | 176 | `~` | Tilde |
| 127 | 7F | 177 | DEL | Delete character |

## Extended ASCII (128-255)

Extended ASCII characters vary by encoding. The most common in Unix/Linux environments is ISO-8859-1 (Latin-1). Here are some commonly used extended characters:

| Dec | Hex | Char | Description |
|-----|-----|------|-------------|
| 160 | A0 | ` ` | Non-breaking space |
| 161 | A1 | `¡` | Inverted exclamation |
| 162 | A2 | `¢` | Cent sign |
| 163 | A3 | `£` | Pound sign |
| 164 | A4 | `¤` | Currency sign |
| 165 | A5 | `¥` | Yen sign |
| 169 | A9 | `©` | Copyright sign |
| 174 | AE | `®` | Registered sign |
| 176 | B0 | `°` | Degree sign |
| 177 | B1 | `±` | Plus-minus sign |
| 178 | B2 | `²` | Superscript 2 |
| 179 | B3 | `³` | Superscript 3 |
| 181 | B5 | `µ` | Micro sign |
| 188 | BC | `¼` | One quarter |
| 189 | BD | `½` | One half |
| 190 | BE | `¾` | Three quarters |

## Using ASCII in PSH

### Printing ASCII Characters

```bash
# Using echo with escape sequences
echo -e "\x41"          # Prints 'A' (hex)
echo -e "\0101"         # Prints 'A' (octal — echo -e requires a leading 0; bare \101 is literal, matching bash)
echo -e "\u0041"        # Prints 'A' (Unicode)

# Using printf
printf "\x41\n"         # Prints 'A' (hex)
printf "\101\n"         # Prints 'A' (octal)

# Control characters
echo -e "\a"            # Bell (ASCII 7)
echo -e "\b"            # Backspace (ASCII 8)
echo -e "\t"            # Tab (ASCII 9)
echo -e "\n"            # Newline (ASCII 10)
```

> **Note:** PSH's `printf "%c" 65` interprets the number as an ASCII code and prints 'A'. In bash, `printf "%c" 65` prints '6' (first character of the string "65"). This is a behavioral difference.

### Character Code Conversions

```bash
# Convert ASCII value to character
ascii=65
printf "%c\n" $ascii    # Prints 'A'

# Hex to character
printf "\x41\n"          # Prints 'A'
```

> **Note:** The bash syntax `printf "%d" "'A"` (character to ASCII value) is not supported in PSH.

## Escape Sequences

PSH supports various escape sequences in strings:

### Standard C-style Escapes

| Sequence | ASCII | Description | Example |
|----------|-------|-------------|---------|
| `\a` | 7 | Alert (bell) | `echo -e "\a"` |
| `\b` | 8 | Backspace | `echo -e "abc\b"` |
| `\e` | 27 | Escape (supported in `echo -e` and `$'...'`; not in PSH `printf`) | `echo -e "\e[31m"` |
| `\f` | 12 | Form feed | `echo -e "Page\fBreak"` |
| `\n` | 10 | Newline | `echo -e "Line1\nLine2"` |
| `\r` | 13 | Carriage return | `echo -e "abc\rXYZ"` |
| `\t` | 9 | Horizontal tab | `echo -e "Col1\tCol2"` |
| `\v` | 11 | Vertical tab | `echo -e "Line1\vLine2"` |
| `\\` | 92 | Backslash | `echo -e "C:\\path"` |
| `\"` | 34 | Double quote | `echo -e "\"quoted\""` |
| `\'` | 39 | Single quote | `echo -e "\'quoted\'"` |

### Numeric Escapes

| Format | Description | Example | Result |
|--------|-------------|---------|--------|
| `\nnn` | Octal (3 digits) | `\101` | `A` |
| `\0nnn` | Octal (bash format) | `\0101` | `A` |
| `\xhh` | Hexadecimal | `\x41` | `A` |
| `\uhhhh` | Unicode (4 hex) | `\u0041` | `A` |
| `\Uhhhhhhhh` | Unicode (8 hex) | `\U00000041` | `A` |

## Character Conversions

### Case Conversion

```bash
# Using parameter expansion
str="Hello World"
echo "${str^^}"    # HELLO WORLD (uppercase)
echo "${str,,}"    # hello world (lowercase)
echo "${str^}"     # Hello World (capitalize first)
```

### Character Classification

```bash
# Check if character is alphabetic (using pattern matching)
is_alpha() {
    [[ "$1" =~ ^[a-zA-Z]$ ]]
}

# Check if character is a digit
is_digit() {
    [[ "$1" =~ ^[0-9]$ ]]
}

# Check if string is alphanumeric
is_alnum() {
    [[ "$1" =~ ^[a-zA-Z0-9]+$ ]]
}
```

## Practical Examples

### ROT13 Cipher

```bash
# ROT13 using tr (the standard Unix approach)
rot13() {
    echo "$1" | tr 'A-Za-z' 'N-ZA-Mn-za-m'
}

# Usage
rot13 "Hello World"  # Outputs: Uryyb Jbeyq
rot13 "Uryyb Jbeyq"  # Outputs: Hello World
```

### ASCII Art Box

```bash
# Draw a box using ASCII characters
draw_box() {
    local width=${1:-20}
    local height=${2:-5}
    local i
    
    # Top border
    printf "\u250C"  # ┌
    for ((i = 0; i < width - 2; i++)); do
        printf "\u2500"  # ─
    done
    printf "\u2510\n"  # ┐
    
    # Middle rows
    for ((i = 0; i < height - 2; i++)); do
        printf "\u2502"  # │
        printf "%*s" $((width - 2)) ""
        printf "\u2502\n"  # │
    done
    
    # Bottom border
    printf "\u2514"  # └
    for ((i = 0; i < width - 2; i++)); do
        printf "\u2500"  # ─
    done
    printf "\u2518\n"  # ┘
}
```

### Character Counter

```bash
# Count unique characters in text using fold, sort, and uniq
char_count() {
    echo "Character frequencies in: $1"
    echo "$1" | fold -w 1 | sort | uniq -c | sort -rn
}

# Usage
char_count "hello world"
```

### Terminal Color Codes

ANSI color codes use escape sequences to change terminal text colors. While PSH does not currently support `\e` or `\033` escape sequences in `echo -e` or `printf`, these codes are documented here for reference as they are used extensively in shell scripting.

```
# ANSI color escape sequence format:
# \e[CODEm or \033[CODEm

# Foreground colors (30-37):
30 = Black    31 = Red      32 = Green    33 = Yellow
34 = Blue     35 = Magenta  36 = Cyan     37 = White

# Bright foreground (90-97):
90 = Bright Black   91 = Bright Red   92 = Bright Green
93 = Bright Yellow  94 = Bright Blue  95 = Bright Magenta

# Background colors (40-47):
40 = Black    41 = Red      42 = Green    43 = Yellow
44 = Blue     45 = Magenta  46 = Cyan     47 = White

# Reset: \e[0m
```

## ASCII Quick Reference

### Common Control Characters
```
Ctrl+C  (3)   - Interrupt
Ctrl+D  (4)   - EOF
Ctrl+G  (7)   - Bell
Ctrl+H  (8)   - Backspace
Ctrl+I  (9)   - Tab
Ctrl+J  (10)  - Newline
Ctrl+L  (12)  - Clear screen
Ctrl+M  (13)  - Carriage return
Ctrl+Z  (26)  - Suspend
Esc     (27)  - Escape
```

### Character Ranges
```
0-31    Control characters
32-126  Printable ASCII
48-57   Digits (0-9)
65-90   Uppercase (A-Z)
97-122  Lowercase (a-z)
127     Delete
128-255 Extended ASCII
```

### Useful ASCII Values
```
Space   32  (0x20)
!       33  (0x21)
"       34  (0x22)
#       35  (0x23)
$       36  (0x24)
'       39  (0x27)
*       42  (0x2A)
/       47  (0x2F)
:       58  (0x3A)
<       60  (0x3C)
>       62  (0x3E)
?       63  (0x3F)
@       64  (0x40)
[       91  (0x5B)
\       92  (0x5C)
]       93  (0x5D)
`       96  (0x60)
{       123 (0x7B)
|       124 (0x7C)
}       125 (0x7D)
~       126 (0x7E)
```

This ASCII reference is essential for shell scripting tasks involving text processing, character manipulation, and terminal control sequences.