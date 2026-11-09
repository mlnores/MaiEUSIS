"""Read cached XLSX values using the standard library; never modify source files."""
from pathlib import Path
from zipfile import ZipFile
import math
import posixpath
import re
import xml.etree.ElementTree as ET

NS={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
TAG='{'+NS['m']+'}'
REL='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'


class Workbook:
    def __init__(self,path):
        self.path=Path(path);self.archive=ZipFile(path);self.strings=[]
        rels={e.get('Id'):e.get('Target') for e in ET.fromstring(self.archive.read('xl/_rels/workbook.xml.rels'))}
        self.sheets={}
        for el in ET.fromstring(self.archive.read('xl/workbook.xml')).findall('m:sheets/m:sheet',NS):
            target=rels[el.get(REL)]
            self.sheets[el.get('name')]=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
        if 'xl/sharedStrings.xml' in self.archive.namelist():
            for _,el in ET.iterparse(self.archive.open('xl/sharedStrings.xml'),events=['end']):
                if el.tag==TAG+'si':
                    self.strings.append(''.join(t.text or '' for t in el.iter(TAG+'t')));el.clear()

    def close(self):self.archive.close()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()

    def rows(self,sheet):
        for _,el in ET.iterparse(self.archive.open(self.sheets[sheet]),events=['end']):
            if el.tag!=TAG+'row':continue
            row=[]
            for cell in el:
                index=0
                for a in re.match(r'[A-Z]+',cell.get('r')).group():index=26*index+ord(a)-64
                while len(row)<index:row.append(None)
                node=cell.find('m:v',NS);value=node.text if node is not None else None;kind=cell.get('t')
                if kind=='s' and value is not None:value=self.strings[int(value)]
                elif kind=='inlineStr':value=''.join(t.text or '' for t in cell.iter(TAG+'t'))
                elif value is not None and kind not in {'str','e','d'}:
                    value=float(value)
                    if not math.isfinite(value):value=None
                    elif value.is_integer():value=int(value)
                    if kind=='b' and value is not None:value=bool(value)
                row[index-1]=value
            el.clear()
            if any(v is not None for v in row):yield row

    def records(self,sheet):
        rows=self.rows(sheet);header=next(rows)
        if len(header)!=len(set(header)):raise ValueError('Duplicate workbook columns: '+sheet)
        for row in rows:yield dict(zip(header,row))
