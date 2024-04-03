import unidiff
import os


def _diff_patch_lines(patch):
    line_num_added = []
    line_num_removed = []
    line_content_added = []
    line_content_removed = []
    for hunk in patch:
        if hunk.added > 0:
            targets = hunk.target
            target_start = hunk.target_start
            for i in range(0, len(targets)):
                if targets[i].startswith('+') and not targets[i][1:].strip().startswith(('*', '//', 'import ')) and targets[i][1:].strip():
                    line_num_added.append(target_start + i)
                    line_content_added.append(targets[i][1:])
        if hunk.removed > 0:
            sources = hunk.source
            source_start = hunk.source_start
            for i in range(0, len(sources)):
                if sources[i].startswith('-') and not sources[i][1:].strip().startswith(('*', '//', 'import ')) and sources[i][1:].strip():
                    line_num_removed.append(source_start + i)
                    line_content_removed.append(sources[i][1:])
    return line_num_added, line_content_added, line_num_removed, line_content_removed


def get_diff_info(file_path):
    patch_results = {}
    with open(file_path, encoding='UTF-8') as f:
        diff_text = f.read()
    patch_set = unidiff.PatchSet(diff_text)
    for patch in patch_set:
        if '.git' in patch.path or os.path.join('src', 'test') in patch.path or (not patch.path.endswith(('.java', '.xml'))):
            continue
        line_num_added, line_content_added, line_num_removed, line_content_removed = _diff_patch_lines(patch)
        java_file_path = patch.path
        patch_results[java_file_path] = {
            'line_num_added': line_num_added,
            'line_content_added': line_content_added,
            'line_num_removed': line_num_removed,
            'line_content_removed': line_content_removed
        }
    return patch_results


if __name__ == '__main__':
    print('jcci')

