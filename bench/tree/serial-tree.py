# -*- coding: utf-8 -*-
from treeTester import *
import sys
import cProfile

def main():
    executeTree()

if __name__=="__main__":
    importTree(sys.argv[1] if len(sys.argv) > 1 else "tree.txt")
    registerMap(map)
    main()
