from json import loads, JSONDecodeError, load, dump, dumps
from http.client import HTTPSConnection
from urllib.parse import urlparse, urlencode
from sys import platform
from os import getenv, chdir, mkdir, remove, system
from os.path import join, exists, dirname, expanduser
from datetime import datetime, timezone, timedelta
from re import match

from time import time

api = "https://api.clockify.me/api/v1"
host = "api.clockify.me"

max_table_width = 100

time_api = "http://worldtimeapi.org/api/timezone/"
time_host = "worldtimeapi.org"

if platform.startswith("win32"):
	config_path = getenv("userprofile")
	clear = lambda: system("cls")
elif platform.startswith("linux"):
	config_path = expanduser("~")
	clear = lambda: system("clear")

config_dir = ".clockify"
config_file = "clockify.json"

tab = lambda string, size = 3: string.expandtabs(size)

class ClockifyClientException(Exception): pass
class LocalTimeException(Exception): pass

class Session(HTTPSConnection):
	def __init__(self, *args, **kwargs):
		self.headers = {}

		self.headers.update({
			"Connection": "keep-alive", 
			"Content-type": "application/x-www-form-urlencoded"
		})

		super().__init__(*args, **kwargs)

	def get(self, url, params={}, headers={}, showerror=False):
		if headers:
			self.headers.update(headers)
		
		if params:
			params = urlencode(params)
			url = f"{url}?{params.replace('_', '-', params.count('_'))}"

		self.request("GET", url, None, self.headers)

		response = self.getresponse()

		if response.status != 200:
			if showerror:
				response.read()
				return response.status
			try:
				json = loads(response.read())

				if "message" in json and "code" in json:
					raise ClockifyClientException(f"{json['message']} ({json['code']})")
				elif "error" in json and "status" in json:
					raise ClockifyClientException(f"HTTP request error: {json['status']} ({json['error']})")
				else:
					raise ClockifyClientException(response.status)

			except JSONDecodeError:
				raise ClockifyClientException(response.status)

		return loads(response.read())

class LocalTime:
	def __init__(self, timezone):
		session = HTTPSConnection(time_host)

		session.request("GET", f"{time_api}{timezone}", None, {})

		response = session.getresponse()

		if response.status != 200:
			try:
				json = loads(response.read())
			except JSONDecodeError:
				raise LocalTimeException(f"an error occured during using api {time_host}")

			if "error" in json:
				raise LocalTimeException(json["error"])

		json = loads(response.read())

		for item in json:
			self.__setattr__(item, json[item])

class TimeEntry:
	def __init__(self, client, json, session):
		self.client = client
		self.session = session

		for item in json:
			if item == "timeInterval":
				json["timeInterval"]["start"] += "+00:00"
				json["timeInterval"]["end"] += "+00:00"

			self.__setattr__(item, json[item])

	def GetLinkedTask(self):
		self.workspace = self.client.GetWorkspaceByID(self.workspaceId)

		if self.workspace:
			project = self.workspace.GetProjectByID(self.projectId)

			if project:
				task = project.GetTaskByID(self.taskId)

				if task:
					return task


	def __repr__(self):
		return f"<{self.__class__.__qualname__} description='{self.description}'>"

class User:
	def __init__(self, client, json, session):
		self.client = client
		self.session = session

		for item in json: self.__setattr__(item, json[item])

	def GetTimeEntryOnWorkspace(self, workspace=None):
		if workspace:
			if type(workspace) == Workspace:
				workspace = workspace.id
		else:
			workspace = self.activeWorkspace

		entries = []

		response = self.session.get(f"{api}/workspaces/{workspace}/user/{self.id}/time-entries")

		if response:
			for entry in response:
				entries.append(TimeEntry(self.client, entry, self.session))

		return entries

	def __repr__(self):
		return f"<{self.__class__.__qualname__} name='{self.name}'>"

class Task:
	def __init__(self, client, json, session, project):
		self.client = client

		for item in json: self.__setattr__(item, json[item])

		self.project = project

	def __repr__(self):
		return f"<{self.__class__.__qualname__} name='{self.name if len(self.name) <= 50 else self.name[: 50] + '...'}', project='{self.project.name}', workspace='{self.project.workspace.name}'>"

class Project:
	def __init__(self, client, json, session, workspace):
		self.client = client
		self.session = session

		for item in json: self.__setattr__(item, json[item])

		self.workspace = workspace

	def GetTasksOnProject(self, **kwargs):
		response = self.session.get(f"{api}/workspaces/{self.workspace.id}/projects/{self.id}/tasks", params=kwargs)

		tasks = []

		if response:
			for task in response:
				tasks.append(Task(self.client, task, self.session, self))

		return tasks

	def GetTaskByID(self, taskId):
		response = self.session.get(f"{api}/workspaces/{self.workspace.id}/projects/{self.id}/tasks/{taskId}")

		if response:
			return Task(self.client, response, self.session, self)

	def __repr__(self):
		return f"<{self.__class__.__qualname__} name='{self.name}', workspace='{self.workspace.name}'>"

class Workspace:
	def __init__(self, client, json, session):
		self.client = client
		self.session = session

		for item in json: self.__setattr__(item, json[item])

	def GetAllProjects(self, **kwargs):
		response = self.session.get(f"{api}/workspaces/{self.id}/projects", params=kwargs)

		projects = []

		if response:
			for project in response:
				projects.append(Project(self.client, project, self.session, self))

		return projects

	def GetProjectByID(self, projectId):
		response = self.session.get(f"{api}/workspaces/{self.id}/projects/{projectId}")

		if response:
			return Project(self.client, response, self.session, self)


	def __repr__(self):
		return f"<{self.__class__.__qualname__} name='{self.name}'>"

class Clockify:
	def __init__(self, apikey):
		self.session = Session(host)
		self.session.headers.update({
			"X-Api-Key": apikey
		})

	def GetAllMyWorkspaces(self):
		response = self.session.get(f"{api}/workspaces")
		workspaces = []

		if response:
			for workspace in response:
				workspaces.append(Workspace(self, workspace, self.session))

		return workspaces

	def GetWorkspaceByID(self, workspaceId):
		workspaces = self.GetAllMyWorkspaces()

		for workspace in workspaces:
			if workspaceId == workspace.id:
				return workspace

	def GetUserInfo(self):
		response = self.session.get(f"{api}/user")

		if response:
			return User(self, response, self.session)

class CLI:
	def __init__(self):
		self.Reload()

		self.config = self.LoadConfig()

		while not self.ValidateAuthKey(self.config["key"]):
			# self.Reload()
			self.config = self.CreateConfig(f"Stored auth-key is not valid")

		self.client = Clockify(self.config["key"])

		self.workspace = None
		self.project = None

		if self.client.GetUserInfo().name:
			print(tab(f"\n\tWelcome back, {self.client.GetUserInfo().name}"))

		self.SetWorkspace()

	def ValidateAuthKey(self, key):
		session = Session(host)
		session.headers.update({
			"X-Api-Key": key
		})

		response = session.get(f"{api}/workspaces", showerror=True)

		session.close()

		if response == 401:
			return False
		else:
			return True

	def Logo(self):
		print("\n\n\t .o88b. db       .d88b.   .o88b. db   dD d888888b d88888b db    db") 
		print("\td8P  Y8 88      .8P  Y8. d8P  Y8 88 ,8P'   `88'   88'     `8b  d8'") 
		print("\t8P      88      88    88 8P      88,8P      88    88ooo    `8bd8' ") 
		print("\t8b      88      88    88 8b      88`8b      88    88~~~      88   ") 
		print("\tY8b  d8 88booo. `8b  d8' Y8b  d8 88 `88.   .88.   88         88   ") 
		print("\t `Y88P' Y88888P  `Y88P'   `Y88P' YP   YD Y888888P YP         YP   \n\n") 

	def CreateConfig(self, title="No auth-key found"):
		file = open(config_file, "w")

		print(tab(f"\t{title}"))

		key = input(tab("\tPlease enter your auth-key: "))
		data = {"key": key}

		dump(data, file)
		file.close()

		print(tab(f"\n\tSaved into {join(config_path, config_dir, config_file)}"))

		return data

	def Reload(self):
		clear()
		self.Logo()
		
	def LoadConfig(self):
		chdir(config_path)

		if exists(join(config_path, config_dir)):
			chdir(config_dir)
			if exists(join(config_path, config_dir, config_file)):
				try:
					file = open(config_file, "r")
					json = load(file)
					file.close()
					print(tab(f"\tAuth-key found: {join(config_path, config_dir, config_file)}"))
					return json
				except:
					file.close()
					remove(config_file)
					return self.CreateConfig()
			else:
				return self.CreateConfig()
		else:
			mkdir(config_dir)
			chdir(config_dir)
			return self.CreateConfig()

	def Choice(self, title, hint, elements, ret=False, msg="Ctrl-C to return back"):
		print(tab(f"\n\t{title}{' (' + msg + ')' if ret else ''}:"))
		k = 1
		for element in elements:
			print(tab(f"\t {k}. {element}"))
			k += 1

		try:
			answer = input(tab(f"\n\t{hint}: "))
		except KeyboardInterrupt:
			return -1

		if answer.isnumeric():
			answer = int(answer)
			if 1 <= answer <= len(elements):
				return answer - 1
			if not answer:
				return -1
		self.Reload()

		print(tab("\tWrong input. Try again"))

		return self.Choice(title, hint, elements)

	def SetAction(self, ret=True):
		available = [
			"List tasks",
			"Total report"
		]

		choice = self.Choice("Select action", "Action number", available, ret)

		if choice == -1:
			self.Reload()
			self.SetProject(True)
		elif choice == 0:
			tasks = self.project.GetTasksOnProject()
			width = 100

			sep = tab(f"\t+{'-' * (width - 2)}+")
			
			print("", sep, tab(f"\t| %-{width - 4}s |" % "Available tasks on project"), sep, sep="\n")

			for task in tasks:
				task = task.name
				cell = width - 4
		
				print(tab("".join(f"\t| %-{cell}s |\n" % task[i * cell: i * cell + cell] for i in range(len(task) // cell + (1 if (len(task) % cell) else 0)))), end="")
				print(tab(f"\t| %{cell}s |\n{sep}" % ("")))

			self.SetAction(ret)
		elif choice == 1:
			entries = self.client.GetUserInfo().GetTimeEntryOnWorkspace()
			
			width = 114
			
			date_cell = 10
			time_cell = 8

			entry_cell = width - date_cell - time_cell - 10

			if entry_cell < 10:
				entry_cell = 10

			date = None
			is_date_printed = None

			is_entry_printed = True

			current = None

			sep = tab(f"\t+{'-' * (date_cell + 2)}+{'-' * (entry_cell + 2)}+{'-' * (time_cell + 2)}+")

			print("", sep, tab(f"\t| %-{date_cell}s | %-{entry_cell}s | %-{time_cell}s |" % ("Date", "Entry", "Time")), sep="\n")

			for entry in entries:
				current = datetime.fromisoformat(entry.timeInterval["start"]).date()

				if date != current:
					is_date_printed = True
					print(sep)

					date = current
				else:
					print(tab(f"\t| { ' ' * date_cell} +{'-' * (entry_cell + 2)}+{'-' * (time_cell + 2)}+"), end=tab("\t"))

				row = []
				entry_task = entry.GetLinkedTask()

				duration = match(r"(pt|PT)?((?P<hours>\d{1,2})[hH])?((?P<minutes>\d{1,2})[mM])?((?P<seconds>\d{1,2})[sS])?", entry.timeInterval["duration"]).groupdict()

				duration = {item: int(duration[item] if duration[item] else 0) for item in duration}

				is_entry_printed = True

				for i in range(len(entry_task.name) // entry_cell + (1 if (len(entry_task.name) % entry_cell) else 0) + 1):
					row.append(f"\t| %-{date_cell}s | %-{entry_cell}s | %-{time_cell}s |\n" % ((current.strftime("%d.%m.%Y") if is_date_printed else ""), entry_task.name[i * entry_cell: i * entry_cell + entry_cell], (timedelta(hours=duration["hours"], minutes=duration["minutes"], seconds=duration["seconds"]) if is_entry_printed  else "")))
					is_date_printed = False
					is_entry_printed = False

				print(tab("".join(row)), end="")

			print(sep)

			self.SetAction(ret)

	def SetProject(self, ret=True):
		if self.project: self.Reload()
		if self.workspace:
			print(tab(f"\tCurrent workspace \"{self.workspace.name}\""))

		available = self.workspace.GetAllProjects()
		choice = self.Choice("Select project", "Project number", [project.name for project in available], ret)

		if choice == -1:
			self.Reload()
			self.SetWorkspace()
		else:
			self.project = available[choice]

			self.Reload()

			print(tab(f"\tCurrent workspace \"{self.workspace.name}\", project \"{self.project.name}\""))
			self.SetAction(True)

	def SetWorkspace(self, ret=True):
		if self.workspace: self.Reload()

		available = self.client.GetAllMyWorkspaces()
		choice = self.Choice("Select workspace", "Workspace number", [workspace.name for workspace in available], ret, msg="Ctrl-C to exit CLI")

		if choice == -1:
			if self.client.GetUserInfo().name:
				print(tab(f"\n\n\tSee you soon, {self.client.GetUserInfo().name}, bye!"))
			return 0;
		else:
			self.workspace = available[choice]

		self.Reload()

		self.SetProject(True)

CLI()

# client = Clockify("YWMyYmJiNTEtMzVhNy00YzJhLWI2MmEtYmU5ZWNlMDlmZmJi")

# user = client.GetUserInfo()

# session = Session("worldtimeapi.org")

# last = None
# curr = None

# for i in user.GetTimeEntryOnWorkspace():
# 	curr = datetime.fromisoformat(i.timeInterval["start"]).astimezone(timezone(timedelta(hours=3))).date()

# 	if last != curr:
		
# 		if last:
# 			print("\nDate changed!")

# 		else:
# 			print("Start date!")

# 		last = curr


# 	print(curr)


# print(session.get(f"http://worldtimeapi.org/api/timezone/{user.settings['timeZone']}", headers={"User-Agent": "Mozilla/5.0"}))

# x = LocalTime("Europe/Kiev")

# print(int(x.utc_offset[0] + f"{int(x.utc_offset[1:3]) * 60 + int(x.utc_offset[4: ])}"))


# print(dumps(client.GetAllMyWorkspaces()[0].GetAllProjects()[0].GetTasksOnProject(name="4.")[0].json(), ensure_ascii=False))