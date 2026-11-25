import os
import re
import shutil
import json
import traceback

def _read_ini_content(path):
    """Безопасное чтение файла с поддержкой UTF-8 и CP1251"""
    for enc in ('utf-8', 'cp1251'):
        try:
            with open(path, 'r', encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        return f.read()

def should_skip(name):
    return "DISABLED" in name

def find_last_endif_index(lines):
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].lstrip().startswith('endif'):
            return i
    return -1

def ensure_newline_at_end(lines):
    if lines and not lines[-1].endswith('\n'):
        lines[-1] += '\n'

def add_run_to_blend_sections(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        with open(filepath, 'r', encoding='cp1251') as f:
            lines = f.readlines()
    except Exception as e:
        return False, str(e)

    result_lines = []
    section_buffer = []
    section_name = None
    in_section = False
    run_line = "run = CommandList\\Healthbar\\RequestUpdate"

    for line in lines:
        stripped = line.strip()
        is_header = stripped.startswith('[') and stripped.endswith(']')

        if is_header:
            if in_section and section_name:
                if re.search(r'(?<![A-Za-z0-9])blend(?![A-Za-z0-9])', section_name, re.I):
                    already_has = any(run_line in l for l in section_buffer)
                    if not already_has:
                        last_endif = find_last_endif_index(section_buffer)
                        if last_endif != -1:
                            section_buffer.insert(last_endif, run_line + '\n')
                        else:
                            section_buffer.append(run_line + '\n')
                ensure_newline_at_end(section_buffer)
                result_lines.extend(section_buffer)
            elif in_section:
                ensure_newline_at_end(section_buffer)
                result_lines.extend(section_buffer)

            in_section = True
            section_name = stripped[1:-1]
            section_buffer = [line]
        else:
            if in_section:
                section_buffer.append(line)
            else:
                result_lines.append(line)

    if in_section and section_name:
        if re.search(r'(?<![A-Za-z0-9])blend(?![A-Za-z0-9])', section_name, re.I):
            already_has = any(run_line in l for l in section_buffer)
            if not already_has:
                last_endif = find_last_endif_index(section_buffer)
                if last_endif != -1:
                    section_buffer.insert(last_endif, run_line + '\n')
                else:
                    section_buffer.append(run_line + '\n')
        ensure_newline_at_end(section_buffer)
        result_lines.extend(section_buffer)
    elif in_section:
        ensure_newline_at_end(section_buffer)
        result_lines.extend(section_buffer)

    if lines == result_lines:
        return False, "No changes needed"
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(result_lines)
    return True, "Success"

def parse_outfit_file(outfit_file):
    content = _read_ini_content(outfit_file)
    sections = []
    current_section = []
    for line in content.split('\n'):
        line = line.strip()
        if not line: continue
        if line[0].isdigit() and current_section:
            sections.append(current_section)
            current_section = [line]
        else:
            current_section.append(line)
    if current_section:
        sections.append(current_section)
    return sections

def calculate_thresholds(N):
    thresholds = []
    for i in range(1, N):
        threshold = (N - i) / N
        thresholds.append(round(threshold, 2))
    thresholds.append(0.00)
    return thresholds

def create_constants_block(thresholds):
    constants = []
    for i, threshold in enumerate(thresholds, 1):
        constants.append(f"global $health_threshold_{i} = {threshold:.2f}")
    return '\n'.join(constants) + '\n'

def create_present_block(char_name, thresholds, sections):
    present_lines = [f"run = CommandList\\Healthbar\\RequestUpdate", ""]
    N = len(sections)
    for i in range(N):
        if i == 0:
            condition = f"if ($\\Healthbar\\{char_name} > $health_threshold_{i+1})"
        elif i < N - 1:
            condition = f"else if ($\\Healthbar\\{char_name} > $health_threshold_{i+1})"
        else:
            condition = f"else if ($\\Healthbar\\{char_name} <= $health_threshold_{i})"
        present_lines.append(condition)
        for line in sections[i]:
            if line.strip() and not line[0].isdigit():
                present_lines.append("  " + line)
        present_lines.append("")
    present_lines.append("endif")
    present_lines.append("")
    return '\n'.join(present_lines)

def find_next_section(content, start_pos):
    pattern = r'\n\[[^\]]+\]'
    match = re.search(pattern, content[start_pos:])
    if match:
        return start_pos + match.start() + 1
    return -1

def add_health_system(source_ini, target_ini, char_name, sections):
    content = _read_ini_content(source_ini)
    N = len(sections)
    thresholds = calculate_thresholds(N)
    constants_block = create_constants_block(thresholds)
    present_block = create_present_block(char_name, thresholds, sections)
    
    if '[Constants]' in content:
        constants_pos = content.find('[Constants]') + len('[Constants]')
        next_section = find_next_section(content, constants_pos)
        if next_section == -1: next_section = len(content)
        new_content = (content[:next_section] + '\n' + constants_block + content[next_section:])
    else:
        new_content = '[Constants]\n' + constants_block + '\n' + content
    
    if '[Present]' in new_content:
        present_pos = new_content.find('[Present]')
        next_section = find_next_section(new_content, present_pos)
        if next_section == -1: next_section = len(new_content)
        final_content = (new_content[:next_section] + '\n' + present_block + new_content[next_section:])
    else:
        final_content = new_content + '\n[Present]\n' + present_block
    
    with open(target_ini, 'w', encoding='utf-8') as f:
        f.write(final_content)

def process_ini_file(mod_dir, target_file, char_name, log_func=print, L=None):
    """Применяет систему здоровья ТОЛЬКО к выбранному INI-файлу."""
    if L is None: L = {}
    original_dir = os.getcwd()
    
    try:
        os.chdir(mod_dir)
    except Exception as e:
        log_func(f"[ERROR] Не удалось перейти в папку мода '{mod_dir}': {e}")
        return

    try:
        log_func(L.get("log_health_processing_file", "Processing selected file: {}").format(target_file))
        
        # Безопасно создаем путь для бэкапа
        dir_name = os.path.dirname(target_file)
        base_name_only = os.path.basename(target_file)
        backup_name = os.path.join(dir_name, f"DISABLED_{base_name_only}")
        
        shutil.copy2(target_file, backup_name)
        log_func(L.get("log_health_backup_created", "  Backup created: {}").format(backup_name))
        
        # Ищем файлы outfitx.txt в корне папки мода
        outfit_files = sorted([f for f in os.listdir('.') if re.match(r'outfit\d+\.txt', f)], 
                              key=lambda x: int(re.search(r'outfit(\d+)\.txt', x).group(1)))
        
        if not outfit_files:
            log_func(L.get("log_health_no_outfits", "  No outfitx.txt files found!"))
            return
            
        for outfit_file in outfit_files:
            outfit_num = re.search(r'outfit(\d+)\.txt', outfit_file).group(1)
            sections = parse_outfit_file(outfit_file)
            if not sections: continue
            
            base_name = os.path.splitext(target_file)[0]
            new_ini_name = f"{base_name}{outfit_num}.ini"
            
            add_health_system(backup_name, new_ini_name, char_name, sections)
            log_func(L.get("log_health_file_created", "  File created: {}").format(new_ini_name))
            
            res, msg = add_run_to_blend_sections(new_ini_name)
            if res: log_func(L.get("log_health_run_added", "    -> run lines added"))
        
        # Удаляем исходный файл
        if os.path.exists(target_file):
            os.remove(target_file)
            log_func(L.get("log_health_source_deleted", "  Source file deleted: {}").format(target_file))
            
    except Exception as e:
        log_func(f"[CRITICAL] Ошибка в health_system: {e}")
        log_func(traceback.format_exc())
    finally:
        try:
            os.chdir(original_dir)
        except Exception:
            pass
        
def detect_character_name(mod_dir, hash_map_file="character_hashes.json"):
    if not os.path.exists(hash_map_file):
        return None
        
    try:
        with open(hash_map_file, "r", encoding="utf-8") as f:
            hash_map = json.load(f)
    except Exception:
        return None

    # Ищем INI рекурсивно, чтобы найти хэши в подпапках
    ini_files = []
    for root, dirs, files in os.walk(mod_dir):
        for file in files:
            if file.lower().endswith('.ini') and not file.startswith('DISABLED_'):
                ini_files.append(os.path.join(root, file))

    found_hash = None

    for filepath in ini_files:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    match = re.search(r'hash\s*=\s*([a-fA-F0-9]+)', line)
                    if match:
                        file_hash = match.group(1).lower()
                        if file_hash in hash_map:
                            found_hash = file_hash
                            break
        except Exception:
            continue
            
        if found_hash:
            break

    return hash_map.get(found_hash) if found_hash else None