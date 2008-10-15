#!/usr/bin/env python
# vim: set fileencoding=utf8 ts=4 sw=4:

# (c) Sergey Astanin <s.astanin@gmail.com> 2008

#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""usage: gpxplot.py [options] track.gpx

Analyze GPS track and plot elevation and velocity profiles.

Features:
	* using haversine formula to calculate distances (spherical Earth)
	* support of multi-segment (discontinuous) tracks
	* gnuplot support:
		- generate plots if gnuplot.py is available
		- generate gnuplot script if gnuplot.py is not available
		- plot interactively and plot-to-file modes
	* tabular track profile data can be generated
	* metric and English units
	* timezone support

Options:
-h, --help    print this message
-E            use English units (metric units used by default)
-g            plot using gnuplot.py
--gprint      print gnuplot script to standard output
-x var        plot var = { time | distance } against x-axis
-y var        plot var = { elevation | velocity } against y-axis
-o imagefile  save plot to image file (supported: PNG, JPG, EPS, SVG)
-t tzname     use local timezone tzname (e.g. 'Europe/Moscow')
-n N_points   reduce number of points in the plot to approximately N_points
"""

import sys
import datetime
import getopt
from math import sqrt,sin,cos,asin,pi,ceil

import logging
#logging.basicConfig(level=logging.DEBUG,format='%(levelname)s: %(message)s')
debug=logging.debug

try:
	import pytz
except:
	pass

NS='{http://www.topografix.com/GPX/1/0}'
dateformat='%Y-%m-%dT%H:%M:%SZ'

R=6371.0008 # Earth volumetric radius
milesperkm=0.621371192
feetperm=3.2808399

strptime=datetime.datetime.strptime

var_time=2
var_ele=3
var_dist=4
var_vel=5

var_names={ 't': var_time,
			'time': var_time,
			'd': var_dist,
			'dist': var_dist,
			'distance': var_dist,
			'ele': var_ele,
			'elevation': var_ele,
			'a': var_ele,
			'alt': var_ele,
			'altitude': var_ele,
			'v': var_vel,
			'vel': var_vel,
			'velocity': var_vel,
			}

EXIT_EOPTION=1
EXIT_EDEPENDENCY=2
EXIT_EFORMAT=3

def haversin(theta):
	return sin(0.5*theta)**2

def distance(p1,p2):
	lat1,lon1=[a*pi/180.0 for a in p1]
	lat2,lon2=[a*pi/180.0 for a in p2]
	deltalat=lat2-lat1
	deltalon=lon2-lon1
	h=haversin(deltalat)+cos(lat1)*cos(lat2)*haversin(deltalon)
	dist=2*R*asin(sqrt(h))
	return dist

def read_all_segments(trksegs,tzname=None):
	trk=[]
	for seg in trksegs:
		s=[]
		prev_lat,prev_lon,prev_time=None,None,None
		trkpts=seg.findall(NS+'trkpt')
		for pt in trkpts:
			lat=float(pt.attrib['lat'])
			lon=float(pt.attrib['lon'])
			time=pt.findtext(NS+'time')
			if time:
				time=strptime(time,dateformat)
				if tzname:
					time=time.replace(tzinfo=pytz.utc)
					time=time.astimezone(pytz.timezone(tzname))
			ele=pt.findtext(NS+'ele')
			if ele: ele=float(ele)
			s.append([lat, lon, time, ele])
		trk.append(s)
	return trk

def reduce_points(trk,npoints=None):
	count=sum([len(s) for s in trk])
	if npoints:
		ptperpt=1.0*count/npoints
	else:
		ptperpt=1.0
	skip=int(ceil(ptperpt))
	debug('ptperpt=%f skip=%d'%(ptperpt,skip))
	newtrk=[]
	for seg in trk:
		if len(seg) > 0:
			newseg=seg[:-1:skip]+[seg[-1]]
			newtrk.append(newseg)
	debug('original: %d pts, filtered: %d pts'%\
			(count,sum([len(s) for s in newtrk])))
	return newtrk

def eval_dist_velocity(trk):
	dist=0.0
	newtrk=[]
	for seg in trk:
		if len(seg)>0:
			newseg=[]
			prev_lat,prev_lon,prev_time,prev_ele=None,None,None,None
			for pt in seg:
				lat,lon,time,ele=pt
				if prev_lat and prev_lon:
					delta=distance([lat,lon],[prev_lat,prev_lon])
					if time and prev_time:
						vel=3600*delta/((time-prev_time).seconds)
					else: 
						vel=0.0
				else: # new segment
					delta=0.0
					vel=0.0
				dist=dist+delta
				newseg.append([lat,lon,time,ele,dist,vel])
				prev_lat,prev_lon,prev_time=lat,lon,time
			newtrk.append(newseg)
	return newtrk

def read_gpx_trk(filename,tzname=None,npoints=None):
	try:
		import xml.etree.ElementTree as ET
	except:
		try:
			import elementtree.ElementTree as ET
		except:
			try:
				import cElementTree as ET
			except:
				try:
					import lxml.etree as ET
				except:
					print 'this script needs ElementTree (Python>=2.5)'
					sys.exit(EXIT_EDEPENDENCY)
	gpx=open(filename).read()
	etree=ET.XML(gpx)
	trksegs=etree.findall('.//'+NS+'trkseg')
	trk=read_all_segments(trksegs,tzname=tzname)
	trk=reduce_points(trk,npoints=npoints)
	trk=eval_dist_velocity(trk)
	return trk

def print_gpx_trk(trk,file=sys.stdout,metric=True):
	f=file
	if metric:
		f.write('# time(ISO) elevation(m) distance(km) velocity(km/h)\n')
		km,m=1.0,1.0
	else:
		f.write('# time(ISO) elevation(ft) distance(miles) velocity(miles/h)\n')
		km,m=milesperkm,feetperm
	for seg in trk:
		if len(seg) == 0:
			continue
		for p in seg:
			f.write('%s %f %f %f\n'%\
				((p[var_time].isoformat(),\
				m*p[var_ele],km*p[var_dist],km*p[var_vel])))
		f.write('\n')

def gen_gnuplot_script(trk,x,y,file=sys.stdout,metric=True,savefig=None):
	if metric:
		ele_units,dist_units='m','km'
	else:
		ele_units,dist_units='ft','miles'
	file.write("unset key\n")
	if x == var_time:
		file.write("""set xdata time
		set timefmt '%Y-%m-%dT%H:%M:%S'
		set xlabel 'time'\n""")
	else:
		file.write("set xlabel 'distance, %s'\n"%dist_units)
	if y == var_ele:
		file.write("set ylabel 'elevation, %s'\n"%ele_units)
	else:
		file.write("set ylabel 'velocity, %s/h\n"%dist_units)
	if savefig:
		import re
		ext=re.sub(r'.*\.','',savefig.lower())
		if ext == 'png':
			file.write("set terminal png; set output '%s';\n"%(savefig))
		elif ext in ['jpg','jpeg']:
			file.write("set terminal jpeg; set output '%s';\n"%(savefig))
		elif ext == 'eps':
			file.write("set terminal post eps; set output '%s';\n"%(savefig))
		elif ext == 'svg':
			file.write("set terminal svg; set output '%s';\n"%(savefig))
		else:
			print 'unsupported file type: %s'%ext
			sys.exit(EXIT_EFORMAT)
	file.write("plot '-' u %d:%d w l\n"%(x-1,y-1,))
	print_gpx_trk(trk,file=file,metric=metric)
	file.write('e')

def get_gnuplot_script(trk,x,y,metric,savefig):
	import StringIO
	script=StringIO.StringIO()
	gen_gnuplot_script(trk,x,y,file=script,metric=metric,savefig=savefig)
	script=script.getvalue()
	return script

def plot_in_gnuplot(trk,x,y,metric=True,savefig=None):
	script=get_gnuplot_script(trk,x,y,metric,savefig)
	try:
		import Gnuplot
		if not savefig:
			g=Gnuplot.Gnuplot(persist=True)
		else:
			g=Gnuplot.Gnuplot()
		g(script)
	except: # python-gnuplot is not available or is broken
		print 'gnuplot.py is not found'

def print_gnuplot_script(trk,x,y,metric=True,savefig=None):
	script=get_gnuplot_script(trk,x,y,metric,savefig)
	print script

def main():
	metric=True
	gnuplot=False
	gnuplot_print=False
	xvar=var_dist
	yvar=var_ele
	imagefile=None
	tzname=None
	npoints=None
	try: opts,args=getopt.getopt(sys.argv[1:],'hgEx:y:o:t:n:',['help','gprint'])
	except:
		print __doc__
		sys.exit(EXIT_EOPTION)
	for o, a in opts:
		if o in ['-h','--help']:
			print __doc__
			sys.exit(0)
		if o == '-E':
			metric=False
		if o == '-g':
			gnuplot=True
		if o == '--gprint':
			gnuplot_print=True
		if o == '-x':
			if var_names.has_key(a):
				xvar=var_names[a]
			else:
				print 'unknown x variable'
				print __doc__
				sys.exit(EXIT_EOPTION)
		if o == '-y':
			if var_names.has_key(a):
				yvar=var_names[a]
			else:
				print 'unknown y variable'
				print __doc__
				sys.exit(EXIT_EOPTION)
		if o == '-o':
			imagefile=a
		if o == '-t':
			if not globals().has_key('pytz'):
				print 'pytz module is required to change timezone'
				sys.exit(EXIT_EDEPENDENCY)
			tzname=a
		if o == '-n':
			npoints=int(a)
	if len(args) > 1:
		print 'only one GPX file should be specified'
		print __doc__
		sys.exit(EXIT_EOPTION)
	elif len(args) == 0:
		print __doc__
		sys.exit(EXIT_EOPTION)

	file=args[0]
	trk=read_gpx_trk(file,tzname,npoints)
	if gnuplot:
		plot_in_gnuplot(trk,x=xvar,y=yvar,metric=metric,savefig=imagefile)
	elif gnuplot_print:
		print_gnuplot_script(trk,x=xvar,y=yvar,metric=metric,savefig=imagefile)
	else:
		print_gpx_trk(trk,metric=metric)

if __name__ == '__main__':
	main()
