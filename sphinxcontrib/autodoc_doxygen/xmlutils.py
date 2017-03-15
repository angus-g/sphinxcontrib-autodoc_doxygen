from __future__ import print_function, absolute_import, division
from . import get_doxygen_root


def format_xml_paragraph(xmlnode):
    """Format an Doxygen XML segment (principally a detaileddescription)
    as a paragraph for inclusion in the rst document

    Parameters
    ----------
    xmlnode

    Returns
    -------
    lines
        A list of lines.
    """
    return [l.rstrip() for l in _DoxygenXmlParagraphFormatter().generic_visit(xmlnode).lines]


class _DoxygenXmlParagraphFormatter(object):
    # This class follows the model of the stdlib's ast.NodeVisitor for tree traversal
    # where you dispatch on the element type to a different method for each node
    # during the traverse.

    # It's supposed to handle paragraphs, references, preformatted text (code blocks), and lists.

    def __init__(self):
        self.lines = ['']
        self.continue_line = False

    def visit(self, node):
        method = 'visit_' + node.tag
        visitor = getattr(self, method, self.generic_visit)
        return visitor(node)

    def generic_visit(self, node):
        for child in node.getchildren():
            self.visit(child)
        return self

    def visit_ref(self, node):
        ref = get_doxygen_root().findall('.//*[@id="%s"]' % node.get('refid'))
        if ref:
            ref = ref[0]
            if ref.tag == 'memberdef':
                parent = ref.xpath('./ancestor::compounddef/compoundname')[0].text
                name = ref.find('./name').text
                real_name = parent + '::' + name
            elif ref.tag in ('compounddef', 'enumvalue'):
                name_node = ref.find('./name')
                real_name = name_node.text if name_node is not None else ''
            else:
                self.lines[-1] += '(unimplemented link)' + node.text
                return
                raise NotImplementedError(ref.tag)
        else:
            real_name = None

        val = [':cpp:any:`', node.text]
        if real_name:
            val.extend((' <', real_name, '>`'))
        else:
            val.append('`')
        if node.tail is not None:
            val.append(node.tail)

        self.lines[-1] += ''.join(val)

    def para_text(self, text):
        if text is not None:
            if self.continue_line:
                self.lines[-1] += text
            else:
                self.lines.append(text.lstrip())

    def visit_para(self, node):
        self.para_text(node.text)

        # visit children and append tail
        for child in node.getchildren():
            self.visit(child)
            self.para_text(child.tail)
            self.continue_line = True

        self.lines.append('')
        self.continue_line = False

    def visit_formula(self, node):
        text = node.text.strip()

        # detect inline or block math
        if text.startswith('\\[') or not text.startswith('$'):
            if text.startswith('\\['):
                text = text[2:-2]

            self.lines.append('')
            self.lines.append('.. math:: ' + text)
            self.lines.append('')
            self.continue_line = False
        else:
            inline = ':math:`' + node.text.strip()[1:-1].strip() + '`'
            if self.continue_line:
                self.lines[-1] += inline
            else:
                self.lines.append(inline)

            self.continue_line = True

    def visit_parametername(self, node):
        if 'direction' in node.attrib:
            direction = '[%s] ' % node.get('direction')
        else:
            direction = ''

        #self.lines.append('**%s** -- %s' % (
            #node.text, direction))
        self.lines.append(':param %s: %s' % (node.text, direction))
        self.continue_line = True

    def visit_parameterlist(self, node):
        lines = [l for l in type(self)().generic_visit(node).lines if l is not '']
        self.lines.extend([''] + lines + [''])

    def visit_simplesect(self, node):
        if node.get('kind') == 'return':
            self.lines.append(':returns: ')
            self.continue_line = True
        self.generic_visit(node)

    def visit_sect(self, node, char):
        """Generic visit section"""
        title_node = node.find('title')
        if title_node is not None:
            title = title_node.text
            self.lines.append(title)
            self.lines.append(len(title) * char)
            self.lines.append('')

        self.generic_visit(node)

    def visit_sect1(self, node):
        self.visit_sect(node, '=')

    def visit_sect2(self, node):
        self.visit_sect(node, '-')

    def visit_sect3(self, node):
        self.visit_sect(node, '^')

    def visit_sect4(self, node):
        self.visit_sect(node, '"')

    def visit_listitem(self, node):
        self.lines.append('   - ')
        self.continue_line = True
        self.generic_visit(node)

    def visit_preformatted(self, node):
        segment = [node.text if node.text is not None else '']
        for n in node.getchildren():
            segment.append(n.text)
            if n.tail is not None:
                segment.append(n.tail)

        lines = ''.join(segment).split('\n')
        self.lines.extend(('.. code-block:: C++', ''))
        self.lines.extend(['  ' + l for l in lines])

    def visit_computeroutput(self, node):
        c = node.find('preformatted')
        if c is not None:
            return self.visit_preformatted(c)

        self.lines[-1] += '``' + node.text + '``'

    def visit_xrefsect(self, node):
        if node.find('xreftitle').text == 'Deprecated':
            sublines = type(self)().generic_visit(node).lines
            self.lines.extend(['.. admonition:: Deprecated'] + ['   ' + s for s in sublines])
        else:
            raise ValueError(node)

    def visit_subscript(self, node):
        self.lines[-1] += '\ :sub:`%s` %s' % (node.text, node.tail)

    def visit_table(self, node):
        # save the number of columns
        cols = int(node.get('cols'))
        table = []
        # save the current output
        lines = self.lines

        # get width of each column
        widths = [0] * cols

        # build up the table contents
        for row_node in node.findall('row'):
            row = []
            for i, entry in enumerate(row_node.getchildren()):
                self.lines = ['']
                self.generic_visit(entry)
                row.append(self.lines)

                # find width of this entry (including leading and trailing space)
                widths[i] = max(widths[i], max([len(line) for line in self.lines]) + 2)

            table.append(row)

        def append_row(row):
            # find number of lines in row
            num_lines = max([len(e) for e in row])
            lines = []

            for k in range(num_lines):
                line = '|'
                for i, e in enumerate(row):
                    if k < len(e):
                        # this is a valid line
                        line += ' ' + e[k]
                        # pad rest of line
                        line += ' ' * (widths[i] - len(e[k]) - 1)
                    else:
                        # invalid line, just fill with spaces
                        line += ' ' * widths[i]

                    line += '|'

                lines.append(line)

            return lines

        self.lines = lines
        # start with a blank
        self.lines.append('')

        # usual separator line
        sep = '+'
        for width in widths:
            sep += '-' * width
            sep += '+'

        self.lines.append(sep)

        # header row
        self.lines.extend(append_row(table[0]))
        # header separator uses '=' instead of '-'
        self.lines.append(sep.replace('-', '='))

        # loop over body rows
        for row in table[1:]:
            self.lines.extend(append_row(row))
            self.lines.append(sep)

        # end with a blank
        self.lines.append('')
