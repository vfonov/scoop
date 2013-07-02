#
#    This file is part of Scalable COncurrent Operations in Python (SCOOP).
#
#    SCOOP is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Lesser General Public License as
#    published by the Free Software Foundation, either version 3 of
#    the License, or (at your option) any later version.
#
#    SCOOP is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#    GNU Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public
#    License along with SCOOP. If not, see <http://www.gnu.org/licenses/>.
#
"""
Example of object manipulation.
"""
from scoop import futures


class myClass(object):
    def __init__(self):
        self.myVar = 5

def modifyClass(myInstance):
    myInstance.myVar += 1
    return myInstance


def main():
    myInstances = [myClass() for _ in range(20)]
    myAnswers = list(futures.map(modifyClass, myInstances))

    print(myAnswers)
    print([a.myVar for a in myAnswers])


if __name__ == "__main__":
    main()
