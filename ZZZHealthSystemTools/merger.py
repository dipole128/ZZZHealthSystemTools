import os
import sys
import glob
import shutil
import re
import traceback
from datetime import datetime

# Windows: кириллица в print не должна ломать консоль
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


def read_file(filename):
    for enc in ('utf-8', 'cp1251'):
        try:
            with open(filename, 'r', encoding=enc) as f:
                return f.readlines()
        except UnicodeDecodeError:
            continue
    with open(filename, 'r', encoding='utf-8', errors='replace') as f:
        return f.readlines()


def write_file(filename, lines):
    with open(filename, 'w', encoding='utf-8') as f:
        f.writelines(lines)


def split_sections(lines):
    """Возвращает список секций: {'name', 'name_lower', 'start', 'end'}.
    start — индекс строки [Name], end — индекс строки следующего [ или len(lines)."""
    sections = []
    current = None
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith('[') and s.endswith(']'):
            if current is not None:
                current['end'] = i
                sections.append(current)
            current = {
                'name': s[1:-1],
                'name_lower': s[1:-1].lower(),
                'start': i,
                'end': None,
            }
    if current is not None:
        current['end'] = len(lines)
        sections.append(current)
    return sections


def get_section_lines(lines, sections, name_lower):
    for sec in sections:
        if sec['name_lower'] == name_lower:
            return lines[sec['start'] + 1:sec['end']]
    return None


HEALTH_IF_RE    = re.compile(r'^\s*if\s*\(\s*\$?\\+Healthbar\\+\w+')
ENDIF_RE        = re.compile(r'^endif\b')
ELSE_IF_RE      = re.compile(r'^else\s+if\b')
ELSE_RE         = re.compile(r'^else\b')
IF_RE           = re.compile(r'^if\b')
THRESHOLD_DEF_RE = re.compile(
    r'^\s*global\s+(?:persist\s+)?\$health_threshold_(\w+)\s*=\s*(.+?)\s*$'
)
THRESHOLD_USE_RE = re.compile(r'(\$health_threshold_)(\w+)')

PRESERVE_DIRECTIVES = {
    'post $active0 = 0',
    'run = CommandList\\Healthbar\\RequestUpdate',
}


def find_health_block(present_lines):
    """Возвращает (start, end_exclusive) первого health-блока.
    Учитывает вложенность if/endif; else if и else не считаются за новый уровень."""
    start = None
    for i, line in enumerate(present_lines):
        if HEALTH_IF_RE.match(line):
            start = i
            break
    if start is None:
        return None, None

    depth = 0
    for i in range(start, len(present_lines)):
        stripped = present_lines[i].strip()
        if ENDIF_RE.match(stripped):
            depth -= 1
            if depth == 0:
                return start, i + 1
        elif ELSE_IF_RE.match(stripped) or ELSE_RE.match(stripped):
            pass
        elif IF_RE.match(stripped):
            depth += 1
    return start, None  # незакрытый блок — вернёт None, обработаем как ошибку


def process_source(fname):
    lines = read_file(fname)
    sections = split_sections(lines)

    # Собираем ВСЕ секции [Constants], если их несколько
    const_lines = []
    for sec in sections:
        if sec['name_lower'] == 'constants':
            const_lines.extend(lines[sec['start'] + 1:sec['end']])
    present_lines = get_section_lines(lines, sections, 'present')

    thresholds = []
    for line in const_lines:
        m = THRESHOLD_DEF_RE.match(line)
        if m:
            thresholds.append((m.group(1), m.group(2)))

    has_swapvar = False
    if present_lines:
        has_swapvar = any('swapvar' in l.lower() for l in present_lines)

    health_block   = []
    randomizer     = []
    preserve       = []
    health_missing = True

    if present_lines is not None:
        h_start, h_end = find_health_block(present_lines)
        if h_start is not None and h_end is not None:
            health_missing = False
            for line in present_lines[:h_start] + present_lines[h_end:]:
                if line.strip() in PRESERVE_DIRECTIVES:
                    preserve.append(line)
                else:
                    randomizer.append(line)
            health_block = present_lines[h_start:h_end]
        else:
            for line in present_lines:
                if line.strip() in PRESERVE_DIRECTIVES:
                    preserve.append(line)
                else:
                    randomizer.append(line)

    return {
        'filename':     fname,
        'lines':        lines,
        'sections':     sections,
        'const_lines':  const_lines,
        'present_lines': present_lines,
        'thresholds':   thresholds,
        'health_block': health_block,
        'randomizer':   randomizer,
        'preserve':     preserve,
        'health_missing': health_missing,
        'has_swapvar':  has_swapvar,
    }


def rename_thresholds(block, source_num):
    return [THRESHOLD_USE_RE.sub(lambda m: f'{m.group(1)}{source_num}_{m.group(2)}', line)
            for line in block]


def is_swapset_decl(line, var):
    pat = re.compile(r'^\s*global\s+(?:persist\s+)?' + re.escape(var) + r'\b', re.IGNORECASE)
    return pat.match(line) is not None


def process_merge(mod_dir, sources, out_name, swapset_var, key, back_key, log_func=print, L=None):
    """Функция для вызова из GUI. Принимает пути и параметры."""
    if L is None: L = {}
    original_dir = os.getcwd()
    
    try:
        os.chdir(mod_dir) # Переходим в папку мода, чтобы относительные пути работали
    except Exception as e:
        log_func(f"[ERROR] Не удалось перейти в папку мода '{mod_dir}': {e}")
        return False, str(e)
    
    try:
        log_func(L.get("log_merge_start", "=== Starting merge ==="))
        log_func(L.get("log_merge_base_file", "Base file: {}").format(sources[0]))
        
        if os.path.exists(out_name):
            backup = f"{out_name}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            shutil.copy2(out_name, backup)
            log_func(L.get("log_merge_backup_created", "Backup created: {}").format(backup))

        sources_data = []
        for i, fname in enumerate(sources, 1):
            data = process_source(fname)
            sources_data.append(data)
            log_func(L.get("log_merge_processing_file", "[{}/{}] {}").format(i, len(sources), fname))
            
            status_ok = L.get("log_merge_ok", "OK")
            status_not_found = L.get("log_merge_not_found", "NOT FOUND")
            status_text = status_ok if not data['health_missing'] else status_not_found
            
            log_func(L.get("log_merge_stats", "   thresholds: {}, health block: {}").format(len(data['thresholds']), status_text))
            if data['has_swapvar']:
                log_func(L.get("log_merge_swapvar_warning", "   ⚠ 'swapvar' detected — gating might not be removed!"))

        # --- [Constants] ---
        base = sources_data[0]
        merged_const = ["[Constants]\n"]
        merged_const.append(L.get("log_merge_const_base_comment", "; --- from base (without thresholds and swapset) ---") + "\n")
        seen_globals = set() # Запоминаем уже добавленные переменные
        
        for line in base['const_lines']:
            if THRESHOLD_DEF_RE.match(line): continue
            if is_swapset_decl(line, swapset_var) or is_swapset_decl(line, '$swapset'): continue
            
            # Проверка на дубликаты: извлекаем имя переменной
            match = re.match(r'^\s*global\s+(?:persist\s+)?(\$[a-zA-Z0-9_]+)', line, re.IGNORECASE)
            if match:
                var_name = match.group(1)
                if var_name in seen_globals:
                    continue # Пропускаем, если уже добавили
                seen_globals.add(var_name)
                
            merged_const.append(line)

        merged_const.append(L.get("log_merge_const_health_switch_comment", "\n; --- health system switch ---") + "\n")
        merged_const.append(f"global persist {swapset_var} = 0\n")

        for i, data in enumerate(sources_data, 1):
            if data['thresholds']:
                merged_const.append(L.get("log_merge_const_thresholds_comment", "\n; --- thresholds from source {}: {} ---").format(i, data['filename']) + "\n")
                for suffix, value in data['thresholds']:
                    merged_const.append(f"global $health_threshold_{i}_{suffix} = {value}\n")

        for i, data in enumerate(sources_data[1:], 2):
            randomizer_consts = [
                l for l in data['const_lines']
                if re.match(r'^\s*global\s+(?:persist\s+)?\$(last_|switch_interval)', l)
            ]
            if randomizer_consts:
                log_func(L.get("log_merge_randomizer_warning", "⚠ Source {} ({}) contains randomizer constants — they are NOT copied.").format(i, data['filename']))

        # --- [Present] ---
        merged_present = ["[Present]\n"]
        seen = set()
        for line in base['preserve']:
            if line.strip() not in seen:
                merged_present.append(line)
                seen.add(line.strip())

        merged_present.append(L.get("log_merge_present_dispatcher_comment", "\n; --- health system dispatcher ---") + "\n")
        for i in range(len(sources)):
            kw = "if" if i == 0 else "else if"
            merged_present.append(f"{kw} {swapset_var} == {i}\n")
            merged_present.append(f"run = CommandListSwapset{i+1}\n")
        merged_present.append("endif\n")

        # --- [KeySwapset] ---
        keyswapset = [
            "\n[KeySwapset]\n",
            "condition = $active == 1\n",
            f"key = {key}\n",
            f"back = {back_key}\n",
            "type = cycle\n",
            f"{swapset_var} = " + ",".join(str(n) for n in range(len(sources))) + "\n",
        ]

        # --- [CommandListSwapsetN] ---
        command_lists = []
        for i, data in enumerate(sources_data, 1):
            cmd = [f"\n[CommandListSwapset{i}]\n"]
            if data['randomizer']:
                r = list(data['randomizer'])
                while r and not r[0].strip(): r.pop(0)
                while r and not r[-1].strip(): r.pop()
                cmd.extend(r)
                cmd.append("\n")
            if data['health_block']:
                cmd.extend(rename_thresholds(data['health_block'], i))
                cmd.append("\n")
            command_lists.append(cmd)

        # --- Сборка ---
        output = []
        output.extend(merged_const)
        output.extend(keyswapset)
        output.extend(merged_present)
        for cmd in command_lists:
            output.extend(cmd)

        skip = {'constants', 'present', 'keyswapset'}
        for sec in base['sections']:
            if sec['name_lower'] in skip: continue
            output.extend(base['lines'][sec['start']:sec['end']])

        write_file(out_name, output)

        # --- ОТКЛЮЧЕНИЕ ИСХОДНЫХ ФАЙЛОВ ---
        log_func(L.get("log_merge_disabling_files", "\n=== Disabling source files ==="))
        for fname in sources:
            if not os.path.exists(fname):
                continue
                
            dir_name = os.path.dirname(fname)
            base_name = os.path.basename(fname)
            
            # Пропускаем, если файл уже отключен (на всякий случай)
            if base_name.startswith("DISABLED_"):
                continue
                
            new_name = os.path.join(dir_name, f"DISABLED_{base_name}")
            
            try:
                os.rename(fname, new_name)
                log_func(L.get("log_merge_renamed_file", "  Renamed: {} -> DISABLED_{}").format(fname, base_name))
            except Exception as e:
                log_func(L.get("log_merge_rename_error", "  Error renaming {}: {}").format(fname, e))

        # ----------------------------------

        log_func(L.get("log_merge_done", "✓ Done: {}").format(out_name))
        log_func(L.get("log_merge_cmd_list_count", "CommandListSwapset: {}").format(len(command_lists)))
        log_func(L.get("log_merge_thresholds_count", "Thresholds: {}").format(", ".join(f"src{i}={len(d['thresholds'])}" for i, d in enumerate(sources_data, 1))))
        return True, L.get("msg_merge_success", "Success")

    except Exception as e:
        log_func(L.get("log_merge_error", "ERROR: {}").format(str(e)))
        log_func(traceback.format_exc())
        return False, str(e)
    finally:
        try:
            os.chdir(original_dir) # Возвращаемся обратно
        except Exception:
            pass