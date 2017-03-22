from __future__ import print_function, absolute_import, division

import re

from docutils.parsers.rst import directives
from six import itervalues
from lxml import etree as ET
from sphinx.ext.autodoc import Documenter, AutoDirective, members_option, ALL
from sphinx.errors import ExtensionError

from . import get_doxygen_root
from .xmlutils import format_xml_paragraph, flatten


class DoxygenDocumenter(Documenter):
    # Variables to store the names of the object being documented. modname and fullname are redundant,
    # and objpath is always the empty list. This is inelegant, but we need to work with the superclass.

    fullname = None  # example: "OpenMM::NonbondedForce" or "OpenMM::NonbondedForce::methodName""
    modname = None   # example: "OpenMM::NonbondedForce" or "OpenMM::NonbondedForce::methodName""
    objname = None   # example: "NonbondedForce"  or "methodName"
    objpath = []     # always the empty list
    object = None    # the xml node for the object
    titles_allowed = True

    option_spec = {
        'members': members_option,
    }

    def __init__(self, directive, name, indent=u'', id=None, brief=False, parent=None):
        super().__init__(directive, name, indent)

        self.parent = parent
        if id is not None:
            self.parse_id(id)
        self.brief = brief

    def parse_id(self, id):
        return False

    def parse_name(self):
        """Determine what module to import and what attribute to document.
        Returns True and sets *self.modname*, *self.objname*, *self.fullname*,
        if parsing and resolving was successful.
        """
        # To view the context and order in which all of these methods get called,
        # See, Documenter.generate(). That's the main "entry point" that first
        # calls parse_name(), follwed by import_object(), format_signature(),
        # add_directive_header(), and then add_content() (which calls get_doc())

        # methods in the superclass sometimes use '.' to join namespace/class
        # names with method names, and we don't want that.
        self.name = self.name.replace('.', '::')
        self.fullname = self.name
        self.modname = self.fullname
        self.objpath = []

        if '::' in self.name:
            parts = self.name.split('::')
            self.objname = parts[-1]
        else:
            self.objname = self.name

        return True

    def document_members(self, all_members=False):
        """Generate reST for member documentation.
        If *all_members* is True, do all members, else those given by
        *self.options.members*.
        """
        want_all = all_members or self.options.inherited_members or \
            self.options.members is ALL
        members = all_members
        # find out which members are documentable

        # remove members given by exclude-members
        if self.options.exclude_members:
            members = [(membername, member) for (membername, member) in members
                       if membername not in self.options.exclude_members]

        # document non-skipped members
        memberdocumenters = []
        for (mname, member, isattr) in self.filter_members(members, want_all):
            classes = [cls for cls in itervalues(AutoDirective._registry)
                       if cls.can_document_member(member, mname, isattr, self)]
            if not classes:
                # don't know how to document this member
                continue

            # prefer the documenter with the highest priority
            classes.sort(key=lambda cls: cls.priority)

            documenter = classes[-1](self.directive, mname, indent=self.indent,
                                     id=member.get('id'), brief=self.brief,
                                     parent=self.object)
            memberdocumenters.append((documenter, isattr))

        for documenter, isattr in memberdocumenters:
            documenter.generate(
                all_members=True, real_modname=self.real_modname,
                check_module=False and not isattr)

        # reset current objects
        self.env.temp_data['autodoc:module'] = None
        self.env.temp_data['autodoc:class'] = None


class DoxygenModuleDocumenter(DoxygenDocumenter):
    objtype = 'doxymodule'
    directivetype = 'module'
    domain = 'f'
    priority = 100

    option_spec = {
        'members': members_option,
        'methods': directives.flag,
        'types': directives.flag,
    }

    @classmethod
    def can_document_member(cls, member, membername, isattr, parent):
        # this method is only called from Documenter.document_members
        # when a higher level documenter (module or namespace) is trying
        # to choose the appropriate documenter for each of its lower-level
        # members. Currently not implemented since we don't have a higher-level
        # doumenter like a DoxygenNamespaceDocumenter.
        return False

    def import_object(self):
        """Import the object and set it as *self.object*.  In the call sequence, this
        is executed right after parse_name(), so it can use *self.fullname*, *self.objname*,
        and *self.modname*.

        Returns True if successful, False if an error occurred.
        """
        xpath_query = './compounddef/compoundname[text()="%s"]/..' % self.fullname
        match = get_doxygen_root().xpath(xpath_query)
        if len(match) != 1:
            raise ExtensionError('[autodoc_doxygen] could not find module (fullname="%s"). I tried'
                                 'the following xpath: "%s"' % (self.fullname, xpath_query))

        self.object = match[0]
        return True

    def format_signaure(self):
        return ''

    def format_name(self):
        return self.fullname

    def get_doc(self, encoding):
        if self.brief:
            description = self.object.find('briefdescription')
        else:
            description = self.object.find('detaileddescription')
            # use the brief description if there's no content in the
            # detailed description
            if not len(description) and not description.text.strip():
                description = self.object.find('briefdescription')

        doc = [format_xml_paragraph(description)]

        if not any(len(d.strip()) for d in doc[0]):
            doc.append(['<undocumented>', ''])

        if self.brief:
            # new line to separate from further content
            doc.append(['`More...`_', ''])

        return doc

    def get_object_members(self, want_all):
        pass

    def filter_members(self, members, want_all):
        ret = []
        for (membername, member) in members:
            ret.append((membername, member, False))
        return ret

    def document_members(self, member_type, all_members=False):
        if member_type == 'func':
            all_members = self.object.xpath('./sectiondef[@kind="func" '
                'or @kind="public-static-func"]/memberdef[@kind="function"]')

            members = [(m.find('name').text, m) for m in all_members]

        elif member_type == 'type':
            classes = self.object.findall('./innerclass')
            members = []
            for c in classes:

                class_obj = get_doxygen_root().find('./compounddef[@id="%s"]' % c.get('refid'))
                if class_obj.get('kind') == 'type':
                    members.append((class_obj.find('compoundname').text, class_obj))

        super().document_members(all_members=members)
        # Uncomment to view the generated rst for the class.
        # print('\n'.join(self.directive.result))

    def add_title(self, title, char='='):
        sourcename = self.get_sourcename()

        self.add_line(u'', sourcename)
        self.add_line(char * len(title), sourcename)
        self.add_line(title, sourcename)
        self.add_line(char * len(title), sourcename)
        self.add_line(u'', sourcename)

    def generate(self, more_content=None, real_modname=None,
                 check_module=False, all_members=False):
        if not self.parse_name():
            self.directive.warn("don't know which module to import for autodocumenting %r" % self.name)
            return

        if not self.import_object():
            return

        self.real_modname = real_modname or self.get_real_modname()

        # we can't import anything, since we're not Python
        self.analyzer = None

        if check_module and not self.check_module():
            return

        sourcename = self.get_sourcename()

        # add title
        title = '%s module reference' % self.format_name()
        self.add_title(title, char='=')

        # module directive
        self.add_line(u'.. f:module:: %s' % self.format_name(), sourcename)
        self.add_line(u'', sourcename)

        # brief description
        self.brief = True
        self.add_content(more_content)

        # we want a brief description of types/functions here

        # detailed description
        self.add_line(u'.. _`More...`:', sourcename)
        self.add_title('Detailed Description', char='-')
        self.brief = False
        self.add_content(None)

        if 'types' in self.options:
            self.add_title('Type Documentation', char='-')
            self.document_members('type', all_members)

        # member doc
        if 'methods' in self.options:
            self.add_title('Function/Subroutine Documentation', char='-')
            self.document_members('func', all_members)


class DoxygenMethodDocumenter(DoxygenDocumenter):
    objtype = 'doxymethod'
    directivetype = 'function'
    domain = 'f'
    priority = 100

    @classmethod
    def can_document_member(cls, member, membername, isattr, parent):
        if ET.iselement(member) and member.tag == 'memberdef' and member.get('kind') == 'function':
            return True
        return False

    def add_directive_header(self, sig):
        """Add the directive header and options to the generated content."""
        domain = self.domain
        # use the <type> field, without other information (e.g. public)
        name = self.format_name()
        sourcename = self.get_sourcename()

        # determine which directive to use from the typefield
        typefield = self.get_typefield()
        directive = 'subroutine' if 'subroutine' in typefield else 'function'

        self.add_line(u'.. %s:%s:: %s%s' % (domain, directive, name, sig),
                      sourcename)

    def parse_id(self, id):
        # try to search our parent node instead of the entire tree
        parent = self.parent
        if parent is None:
            parent = get_doxygen_root()

        xp = './/*[@id="%s"]' % id
        match = parent.xpath(xp)
        if len(match) > 0:
            match = match[0]
            self.fullname = match.find('./definition').text.split()[-1]
            self.modname = self.fullname
            self.objname = match.find('./name').text
            self.object = match
        return False

    def import_object(self):
        if ET.iselement(self.object):
            # self.object already set from DoxygenDocumenter.parse_name(),
            # caused by passing in the `id` of the node instead of just a
            # classname or method name
            return True

        return False

    def get_doc(self, encoding):
        doc = [format_xml_paragraph(self.object.find('briefdescription'))]
        # add parameter documentation (in detaileddescription) for main function documentation
        if not self.brief:
            doc += [format_xml_paragraph(self.object.find('detaileddescription'))]

            # add references/referencedby
            references = self.object.findall('references')
            for ref in references:
                name = ref.text
                doc.append([':callto: :f:func:`%s <%s>`' % (name, name.split('::')[-1])])
            referencedby = self.object.findall('referencedby')
            for ref in referencedby:
                name = ref.text
                doc.append([':calledfrom: :f:func:`%s <%s>`' % (name, name.split('::')[-1])])

        return doc

    def get_typefield(self):
        return ' '.join(self.object.find('definition').text.split()[:-1])

    def format_name(self):
        # we just want to get the bare part of the "type" field
        # i.e. subroutine or <type> function
        typefield = self.get_typefield()

        if typefield is None:
            rtype = None
        elif 'function' in typefield:
            # get the return type
            m = re.search(r'(\S+)\s+function', typefield)
            if m:
                rtype = m.group(0)
            else:
                rtype = 'function'
                print('ERROR searching for return type in', typefield)
        else:
            rtype = 'subroutine' if 'subroutine' in typefield else 'unknown'

        signame = ((rtype + ' ') if rtype is not None else '') + self.objname
        return self.format_template_name() + signame

    def format_template_name(self):
        types = [e.text for e in self.object.findall('templateparamlist/param/type')]
        if len(types) == 0:
            return ''
        return 'template <%s>\n' % ','.join(types)

    def format_signature(self):
        args = self.object.find('argsstring').text
        return args

    def document_members(self, all_members=False):
        pass

class DoxygenTypeDocumenter(DoxygenDocumenter):
    objtype = 'doxytype'
    directivetype = 'type'
    domain = 'f'
    priority = 100

    @classmethod
    def can_document_member(cls, member, membername, isattr, parent):
        if ET.iselement(member) and member.tag == 'compounddef' and member.get('kind') == 'type':
            return True
        return False

    def import_object(self):
        if ET.iselement(self.object):
            return True
        return False

    def parse_id(self, id):
        self.object = get_doxygen_root().find('./compounddef[@id="%s"]' % id)
        self.fullname = self.object.find('compoundname').text
        self.modname, self.objname = self.fullname.rsplit('::')

        return False

    def format_name(self):
        return self.objname

    def add_directive_header(self, sig):
        """Add the directive header and options to the generated content."""
        domain = self.domain
        directive = 'type'
        name = self.format_name()
        sourcename = self.get_sourcename()

        self.add_line(u'.. %s:%s:: %s' % (domain, directive, name),
                      sourcename)

    def get_doc(self, encoding):
        desc = [format_xml_paragraph(self.object.find('briefdescription'))]

        for member in self.object.findall('./sectiondef/memberdef'):
            attribs = flatten(member.find('type')).strip().split(', ')
            name = member.find('name').text
            shape = ''
            rest = ''

            # very rudimentary parsing of type attributes
            # into the Fortran domain format
            for word in attribs:
                if word.startswith('dimension'):
                    shape = word[len('dimension'):].replace(':', r'\:')

            extras = [w for w in attribs[1:] if not w.startswith('dimension')]
            if member.get('prot') == 'private':
                extras.append('private')
            if len(extras):
                rest = ' [' + ', '.join(extras) + ']'

            field = ':typefield %s%s %s%s:' % (attribs[0], shape, name, rest)

            # look for the brief description paragraph
            brief = member.find('briefdescription/para')
            if brief is not None:
                field += ' ' + brief.text

            desc.append([field])

        return desc

    def document_members(self, all_members=False):
        pass
